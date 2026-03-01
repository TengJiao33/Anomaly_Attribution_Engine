import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ColumnLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { Map as MapGL, type MapRef } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW_STATE = {
    longitude: 113.935,
    latitude: 22.535,
    zoom: 13,
    pitch: 50,
    bearing: 15,
    maxPitch: 85 // 允许像常规地图一样更自由的俯仰角
};

const CITY_COORDS: Record<string, { longitude: number, latitude: number, zoom: number }> = {
    "shenzhen": { longitude: 113.935, latitude: 22.535, zoom: 13 },
    "beijing": { longitude: 116.397, latitude: 39.908, zoom: 13 },
    "shanghai": { longitude: 121.473, latitude: 31.230, zoom: 13 },
    "guangzhou": { longitude: 113.264, latitude: 23.129, zoom: 13 },
    "chengdu": { longitude: 104.066, latitude: 30.572, zoom: 13 },
    "chongqing": { longitude: 106.551, latitude: 29.563, zoom: 13 }
};

const CITY_RADIUS: Record<string, number> = {
    "shenzhen": 35,
    "beijing": 150,
    "shanghai": 120,
    "guangzhou": 100,
    "chengdu": 80,
    "chongqing": 60
};

// 类型定义
interface UAVPath {
    id: string;
    path: [number, number, number][];
    timestamps: number[];
}

interface PreprocessedData {
    timeRange: { min: number; max: number };
    totalFlights: number;
    sampledFlights: number;
    trajectories: UAVPath[];
}

// 城市数据缓存类型
interface CityData {
    buildings: any;
    poiDemand: any;
    poiSensitive: any;
}

// 动画配置
const ANIMATION_SPEED = 0.016; // 每帧推进 0.016 秒 (以60帧计约等于真实时间的1x速度)
const TRAIL_LENGTH = 1200;  // 拖尾长度（秒），越长拖尾越明显

export default function MapContainer() {
    // ====== 策略一：按需加载 + 缓存 ======
    // 只存储当前城市的数据，不再一次性加载全部
    const [buildingsData, setBuildingsData] = useState<any>(null);
    const [poiDemand, setPoiDemand] = useState<any>(null);
    const [poiSensitive, setPoiSensitive] = useState<any>(null);
    const [trajectories, setTrajectories] = useState<UAVPath[]>([]);
    const [energyData, setEnergyData] = useState<any>(null);
    const [selectedFlight, setSelectedFlight] = useState<any>(null);
    const [isLoadingCity, setIsLoadingCity] = useState(false);

    // Custom Dropdown State
    const [isDropdownOpen, setIsDropdownOpen] = useState(false);

    // 城市列表定义
    const CITIES = [
        { id: "shenzhen", label: "深圳 · 南山" },
        { id: "beijing", label: "北京 · 核心" },
        { id: "shanghai", label: "上海 · 核心" },
        { id: "guangzhou", label: "广州 · 核心" },
        { id: "chengdu", label: "成都 · 核心" },
        { id: "chongqing", label: "重庆 · 主城" }
    ];

    // 城市数据缓存：切换回已访问城市时直接复用，避免重复 fetch
    const dataCacheRef = useRef<Map<string, CityData>>(new Map());

    // ====== 策略二：动画驱动优化 ======
    // currentTime 用 ref 存储，不触发 React 重渲染
    const currentTimeRef = useRef(0);
    const [isPlaying, setIsPlaying] = useState(true);
    const [animationSpeed, setAnimationSpeed] = useState(1);
    const timeRangeRef = useRef({ min: 0, max: 0 });
    const animFrameRef = useRef<number>(0);
    const mapRef = useRef<MapRef>(null);

    // Dashboard metrics 预计算缓存 (按秒存储)
    const metricsRef = useRef<{ active: number[], cumulative: number[], maxActive: number }>({ active: [], cumulative: [], maxActive: 1 });

    // DeckGL 实例 ref，用于直接更新 layer props
    const deckRef = useRef<any>(null);
    // 进度条 DOM ref，用于直接操作 DOM 避免重渲染
    const progressBarRef = useRef<HTMLDivElement>(null);
    const progressTextRef = useRef<HTMLSpanElement>(null);

    // 预计算轨迹在每一秒的活跃数与累计起飞数
    useEffect(() => {
        if (!trajectories.length || timeRangeRef.current.max <= 0) return;

        const maxSec = Math.ceil(timeRangeRef.current.max);
        const active = new Int32Array(maxSec + 1);
        const cum = new Int32Array(maxSec + 1);

        for (const t of trajectories) {
            if (!t.timestamps || t.timestamps.length === 0) continue;
            const startStr = t.timestamps[0];
            const endStr = t.timestamps[t.timestamps.length - 1];

            const startSec = Math.max(0, Math.floor(startStr));
            const endSec = Math.min(maxSec, Math.ceil(endStr));

            if (startSec <= maxSec) cum[startSec] += 1;

            for (let s = startSec; s <= endSec; s++) {
                active[s] += 1;
            }
        }

        let currentCum = 0;
        let maxActive = 0;
        for (let i = 0; i <= maxSec; i++) {
            currentCum += cum[i];
            cum[i] = currentCum;
            if (active[i] > maxActive) maxActive = active[i];
        }

        metricsRef.current = {
            active: Array.from(active),
            cumulative: Array.from(cum),
            maxActive: maxActive || 1
        };
    }, [trajectories]);

    const [currentCity, setCurrentCity] = useState("shenzhen");
    const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

    // 加载单个城市数据（带缓存）
    const loadCityData = useCallback(async (city: string) => {
        // 检查缓存
        const cached = dataCacheRef.current.get(city);
        if (cached) {
            setBuildingsData(cached.buildings);
            setPoiDemand(cached.poiDemand);
            setPoiSensitive(cached.poiSensitive);
            return;
        }

        setIsLoadingCity(true);
        const basePath = `/data/processed/${city}`;
        try {
            const cacheBuster = `?t=${Date.now()}`;
            const [bRes, pDRes, pSRes] = await Promise.all([
                fetch(`${basePath}/buildings_3d.geojson${cacheBuster}`).then(r => r.ok ? r.json() : null),
                fetch(`${basePath}/poi_demand.geojson${cacheBuster}`).then(r => r.ok ? r.json() : null),
                fetch(`${basePath}/poi_sensitive.geojson${cacheBuster}`).then(r => r.ok ? r.json() : null)
            ]);

            const cityData: CityData = {
                buildings: bRes,
                poiDemand: pDRes,
                poiSensitive: pSRes
            };

            // 存入缓存
            dataCacheRef.current.set(city, cityData);

            setBuildingsData(cityData.buildings);
            setPoiDemand(cityData.poiDemand);
            setPoiSensitive(cityData.poiSensitive);
        } catch (e) {
            console.error(`加载城市 ${city} 数据失败`, e);
        } finally {
            setIsLoadingCity(false);
        }
    }, []);

    // 初始加载：只加载默认城市 + 轨迹数据
    useEffect(() => {
        // 加载初始城市
        loadCityData("shenzhen");

        // 加载轨迹数据与能耗预测数据
        (async () => {
            try {
                const [tRes, eRes] = await Promise.all([
                    fetch('/data/processed/trajectories/uav_trajectories.json'),
                    fetch('/data/processed/energy_predictions.json').catch(() => null)
                ]);

                if (eRes && eRes.ok) {
                    const eData = await eRes.json();
                    setEnergyData(eData);
                }

                if (tRes.ok) {
                    const data: PreprocessedData = await tRes.json();
                    timeRangeRef.current = data.timeRange;
                    setTrajectories(data.trajectories);
                    currentTimeRef.current = 0;
                }
            } catch (e) {
                console.error("加载轨迹数据失败", e);
            }
        })();
    }, [loadCityData]);

    const updateDashboardDOM = useCallback((time: number) => {
        const sec = Math.min(Math.floor(time), metricsRef.current.active.length - 1);
        if (sec >= 0) {
            const activeCount = metricsRef.current.active[sec] || 0;
            const cumCount = metricsRef.current.cumulative[sec] || 0;
            const loadPct = Math.min(100, Math.round((activeCount / metricsRef.current.maxActive) * 100));

            const domActive = document.getElementById('dashboard-active-drones');
            if (domActive) domActive.textContent = activeCount.toString();

            const domCum = document.getElementById('dashboard-cumulative-flights');
            if (domCum) domCum.textContent = cumCount.toString();

            const domLoad = document.getElementById('dashboard-airspace-load');
            if (domLoad) domLoad.textContent = `${loadPct}%`;

            const domBar = document.getElementById('dashboard-airspace-bar');
            if (domBar) domBar.style.width = `${loadPct}%`;
        }
    }, []);

    // ====== 动画循环：完全绕过 React 渲染管线 ======
    const animate = useCallback(() => {
        if (timeRangeRef.current.max === 0) {
            animFrameRef.current = requestAnimationFrame(animate);
            return;
        }

        // 直接更新 ref，不触发 setState
        let next = currentTimeRef.current + ANIMATION_SPEED * animationSpeed;
        if (next > timeRangeRef.current.max) next = 0;
        currentTimeRef.current = next;

        // 直接通过 DeckGL 实例更新 TripsLayer 的 currentTime
        // 这完全跳过 React reconciliation，性能极高
        const deck = deckRef.current?.deck;
        if (deck) {
            const currentLayers = deck.props.layers;
            const updatedLayers = currentLayers.map((layer: any) => {
                if (layer?.id === 'uav-trips-layer') {
                    return layer.clone({ currentTime: next });
                }
                return layer;
            });
            deck.setProps({ layers: updatedLayers });
        }

        // 直接操作 DOM 更新进度条，不触发 React 重渲染
        const progress = timeRangeRef.current.max > 0
            ? (next / timeRangeRef.current.max) * 100 : 0;
        if (progressBarRef.current) {
            progressBarRef.current.style.width = `${progress}%`;
        }
        if (progressTextRef.current) {
            progressTextRef.current.textContent = formatElapsed(next);
        }

        // 更新 Dashboard 定制化数据
        updateDashboardDOM(next);

        animFrameRef.current = requestAnimationFrame(animate);
    }, [animationSpeed, updateDashboardDOM]);

    useEffect(() => {
        if (isPlaying) {
            animFrameRef.current = requestAnimationFrame(animate);
        }
        return () => {
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        };
    }, [isPlaying, animate]);

    // 城市切换处理：切换视角 + 按需加载数据
    const handleCityJump = useCallback((city: string) => {
        setCurrentCity(city);
        setIsDropdownOpen(false); // 关闭自定义下拉菜单

        if (CITY_COORDS[city]) {
            setViewState(prev => ({
                ...prev,
                longitude: CITY_COORDS[city].longitude,
                latitude: CITY_COORDS[city].latitude,
            }));
        }
        // 按需加载目标城市数据
        loadCityData(city);
    }, [loadCityData]);

    // 底图加载后修改水体和绿地颜色
    const handleMapLoad = useCallback(() => {
        const map = mapRef.current?.getMap();
        if (!map) return;

        const style = map.getStyle();
        if (!style?.layers) return;

        for (const layer of style.layers) {
            const id = layer.id.toLowerCase();
            // 水体 → 深蓝色
            if (id.includes('water')) {
                if (layer.type === 'fill') {
                    map.setPaintProperty(layer.id, 'fill-color', '#7ab8e0');
                }
            }
            // 绿地/公园 → 深绿色
            if (id.includes('park') || id.includes('green') || id.includes('landcover') || id.includes('landuse')) {
                if (layer.type === 'fill') {
                    map.setPaintProperty(layer.id, 'fill-color', '#a3d9a5');
                    map.setPaintProperty(layer.id, 'fill-opacity', 0.7);
                }
            }
        }
    }, []);

    // ====== 策略三：Layer 对象稳定化 ======
    // ColumnLayer filter 结果缓存
    const sensitivePoints = useMemo(() =>
        poiSensitive?.features?.filter((f: any) => f.geometry.type === 'Point') || [],
        [poiSensitive]
    );

    // 静态 Layer（buildings + POI）用 useMemo 缓存，只在数据变化时重建
    const staticLayers = useMemo(() => [
        // 3D建筑层 - 增强层次感：展示描边避免模糊
        new GeoJsonLayer({
            id: 'buildings-layer',
            data: buildingsData,
            extruded: true,
            filled: true,
            stroked: true,
            wireframe: true, // 开启线框，勾勒3D建筑物边缘，使密集建筑层次更分明
            getFillColor: [170, 180, 195, 230],       // 冷灰蓝色
            getLineColor: [80, 90, 110, 200],         // 较深描边增强轮廓感
            getLineWidth: 1,
            lineWidthMinPixels: 1,
            getElevation: ((d: any) => d.properties.height || 20) as any,
            pickable: true,
            autoHighlight: true,
            highlightColor: [80, 140, 220, 255],
            material: {
                ambient: 0.4,
                diffuse: 0.6,
                shininess: 32,
                specularColor: [220, 230, 240],
            },
        }),

        // POI需求点 - 柔绿圆盘（不再刺眼，样式更统一内敛）
        new GeoJsonLayer({
            id: 'poi-demand-layer',
            data: poiDemand,
            stroked: true,
            filled: true,
            lineWidthMinPixels: 1,
            getPointRadius: 25,
            pointRadiusMinPixels: 4,
            pointRadiusMaxPixels: 16,
            getFillColor: [52, 211, 153, 160],  // 柔和的浅翡翠绿，带透明感
            getLineColor: [5, 150, 105, 220],   // 翠绿色描边增强边缘
            pickable: true,
        }),

        // POI敏感区 - 面状禁飞区（如南山区原有的Polygon类型区域，展示为带高度区域块）
        new GeoJsonLayer({
            id: 'poi-sensitive-poly-layer',
            data: poiSensitive,
            extruded: true,
            getElevation: 80,
            getPointRadius: 0, // 隐蔽当前图层对Point的处理，点统一交由下方的ColumnLayer渲染为带高度的圆柱
            getFillColor: [239, 68, 68, 160], // 柔和化刺眼的鲜红
            getLineColor: [185, 28, 28, 200],
            wireframe: true,
            pickable: true,
        }),

        // POI敏感区 - 点状禁飞柱（将其他城市原为Point的数据强制转为相同表现的圆柱体）
        new ColumnLayer({
            id: 'poi-sensitive-point-layer',
            data: sensitivePoints,
            diskResolution: 24,
            radius: CITY_RADIUS[currentCity] || 35,
            extruded: true,
            pickable: true,
            elevationScale: 1,
            getPosition: (d: any) => d.geometry.coordinates,
            getFillColor: [239, 68, 68, 160], // 对应面状的柔和红
            getLineColor: [185, 28, 28, 200],
            getElevation: 80,
        }),
    ], [buildingsData, poiDemand, poiSensitive, sensitivePoints, currentCity]);

    // TripsLayer 独立 memo，初始 currentTime 为 0，后续通过 deck.setProps 更新
    const tripsLayer = useMemo(() =>
        new TripsLayer({
            id: 'uav-trips-layer',
            data: trajectories,
            getPath: (d: UAVPath) => d.path,
            getTimestamps: (d: UAVPath) => d.timestamps,
            getColor: (d: UAVPath) => {
                if (energyData && energyData[d.id]) {
                    const payload = energyData[d.id].payload;
                    // 以载重分配轨迹颜色，取代先前不合理的电量颜色
                    if (payload >= 0.75) return [236, 72, 153]; // 粉红色(重载)
                    if (payload >= 0.5) return [168, 85, 247];  // 紫色(中等载重)
                    return [14, 165, 233]; // 天蓝色(轻载/空载)
                }
                return [14, 165, 233]; // 默认天蓝色
            },
            widthMinPixels: 2.5,
            trailLength: TRAIL_LENGTH,
            currentTime: currentTimeRef.current,
            shadowEnabled: false,
            opacity: 0.9,
            pickable: true,
            autoHighlight: true,
            highlightColor: [255, 255, 255, 255],
            onClick: (info: any) => {
                if (info.object) {
                    setSelectedFlight(info.object);
                }
            }
        }),
        [trajectories, energyData]
    );

    // 合并所有 layers
    // 每次组件渲染时（如选中飞行器、暂停、修改视角等），都会重新构建 layers 数组，
    // 此时从 ref 中读取最新时间，确保 DeckGL 不会因为旧层数据而导致轨迹消失或回滚老的时间
    const layers = [...staticLayers, tripsLayer ? tripsLayer.clone({ currentTime: currentTimeRef.current }) : undefined].filter(Boolean);

    // ViewState 回调稳定化
    const handleViewStateChange = useCallback(({ viewState }: any) => {
        const { longitude, latitude, zoom, pitch, bearing } = viewState;
        setViewState({ longitude, latitude, zoom, pitch, bearing, maxPitch: INITIAL_VIEW_STATE.maxPitch });
    }, []);

    // 进度条点击处理
    const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        currentTimeRef.current = pct * timeRangeRef.current.max;

        // 立即更新 DOM
        const progress = pct * 100;
        if (progressBarRef.current) {
            progressBarRef.current.style.width = `${progress}%`;
        }
        if (progressTextRef.current) {
            progressTextRef.current.textContent = formatElapsed(currentTimeRef.current);
        }

        // 拖动时同步更新 Dashboard 数据
        updateDashboardDOM(currentTimeRef.current);

        // 当处于暂停状态时，拖动进度条也需立刻刷新 DeckGL 中的时间
        const deck = deckRef.current?.deck;
        if (deck) {
            const currentLayers = deck.props.layers || [];
            const updatedLayers = currentLayers.map((layer: any) => {
                if (layer?.id === 'uav-trips-layer') {
                    return layer.clone({ currentTime: currentTimeRef.current });
                }
                return layer;
            });
            deck.setProps({ layers: updatedLayers });
        }
    }, []);

    return (
        <div
            className="absolute inset-0 z-0"
            style={{ background: '#f0f0f0' }}
            onContextMenu={(e) => e.preventDefault()} // 阻止默认右键菜单，防止拖拽视角时弹出
        >
            <DeckGL
                ref={deckRef}
                initialViewState={viewState}
                controller={{
                    doubleClickZoom: true,
                    touchRotate: true,
                    dragRotate: true, // 开启拖拽旋转，支持360度旋转和俯仰
                    scrollZoom: true,
                    dragPan: true,
                    keyboard: true
                }}
                layers={layers}
                onViewStateChange={handleViewStateChange}
            >
                <MapGL
                    ref={mapRef}
                    mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
                    reuseMaps
                    onLoad={handleMapLoad}
                    maxPitch={INITIAL_VIEW_STATE.maxPitch}
                />
            </DeckGL>

            {/* 无人机详情面板 */}
            {selectedFlight && (
                <div className="absolute bottom-32 left-8 z-30 w-80 bg-white/40 backdrop-blur-2xl border border-white/50 rounded-[2rem] shadow-[0_8px_32px_0_rgba(31,38,135,0.15)] text-slate-800 p-6 pointer-events-auto transition-all animate-in fade-in slide-in-from-left-4 overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-br from-slate-900/5 to-transparent pointer-events-none"></div>
                    <div className="relative z-10">
                        <div className="flex justify-between items-center mb-5 pb-3 border-b border-slate-300/50">
                            <h3 className="text-sm font-black text-slate-700 tracking-wider flex items-center gap-2">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-600">
                                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
                                </svg>
                                无人机档案: {selectedFlight.id}
                            </h3>
                            <button onClick={() => setSelectedFlight(null)} className="text-slate-400 hover:text-slate-600 transition-colors bg-white/50 p-1 rounded-full">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                            </button>
                        </div>
                        {energyData && energyData[selectedFlight.id] ? (() => {
                            const ed = energyData[selectedFlight.id];
                            const timestamps = selectedFlight.timestamps;
                            let idx = timestamps.findIndex((t: number) => t >= currentTimeRef.current);
                            if (idx === -1) idx = timestamps.length - 1;
                            if (idx < 0) idx = 0;
                            const bat = ed.battery[idx];
                            const pwr = ed.power[idx];
                            const startBat = ed.battery[0];
                            const minBat = Math.min(...ed.battery);

                            return (
                                <div className="flex flex-col gap-3.5 text-sm">
                                    <div className="flex justify-between items-center bg-white/60 p-3 rounded-xl border border-white/80 shadow-sm">
                                        <span className="text-slate-600 font-bold tracking-wide text-xs">当前负荷功率</span>
                                        <span className="font-mono text-indigo-700 font-black tracking-wider">{pwr.toFixed(1)} W</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-white/60 p-3 rounded-xl border border-white/80 shadow-sm">
                                        <span className="text-slate-600 font-bold tracking-wide text-xs">出发时电量</span>
                                        <span className="font-mono font-black tracking-wider text-emerald-600">
                                            {startBat.toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center bg-white/60 p-3 rounded-xl border border-white/80 shadow-sm">
                                        <span className="text-slate-600 font-bold tracking-wide text-xs">实时流失电量</span>
                                        <span className="font-mono font-black tracking-wider" style={{ color: bat < 30 ? '#e11d48' : bat < 60 ? '#d97706' : '#059669' }}>
                                            {bat.toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center bg-white/60 p-3 rounded-xl border border-white/80 shadow-sm">
                                        <span className="text-slate-600 font-bold tracking-wide text-xs">预计降落电量</span>
                                        <span className="font-mono font-black tracking-wider" style={{ color: minBat < 30 ? '#e11d48' : minBat < 60 ? '#d97706' : '#059669' }}>
                                            {minBat.toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center bg-white/60 p-3 rounded-xl border border-white/80 shadow-sm">
                                        <span className="text-slate-600 font-bold tracking-wide text-xs">载重状态</span>
                                        <span className="font-mono text-slate-700 font-black tracking-wider bg-slate-200/50 px-2 py-0.5 rounded shadow-inner">{ed.payload} kg</span>
                                    </div>
                                </div>
                            );
                        })() : (
                            <div className="py-6 text-center text-slate-500 font-bold animate-pulse border border-dashed border-slate-300 rounded-xl bg-white/30">
                                正在接入AirLab能耗模型计算...
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* 城市数据加载指示器 */}
            {isLoadingCity && (
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30">
                    <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-700/60 rounded-2xl px-8 py-4 flex items-center gap-3 shadow-2xl">
                        <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                        <span className="text-cyan-300 text-sm font-medium">加载城市数据...</span>
                    </div>
                </div>
            )}

            {/* 视角控制提示 */}
            <div className="absolute top-4 left-4 bg-white/80 backdrop-blur text-slate-700 text-xs px-3 py-1.5 rounded-lg shadow border border-slate-200 z-10 pointer-events-none">
                💡 提示：按住 <span className="font-semibold text-cyan-600">右键</span> 或 <span className="font-semibold text-cyan-600">Ctrl+左键</span> 拖动可360°旋转/调整视角
            </div>

            {/* 底部动画控制条 - 切换为柔和高定玻璃态 */}
            <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-20 pointer-events-auto">
                <div className="bg-white/40 backdrop-blur-2xl border border-white/50 rounded-[2rem] px-8 py-5 flex items-center gap-6 shadow-[0_8px_32px_0_rgba(31,38,135,0.15)] min-w-[580px] relative">
                    {/* 微弱暗色渐变垫底 */}
                    <div className="absolute inset-0 rounded-[2rem] bg-gradient-to-t from-slate-900/5 to-transparent pointer-events-none overflow-hidden" style={{ zIndex: 0 }}></div>

                    {/* 播放/暂停按钮 */}
                    <button
                        onClick={() => setIsPlaying(!isPlaying)}
                        className="relative z-10 w-12 h-12 rounded-full bg-white/60 border border-white/80 backdrop-blur-md flex items-center justify-center hover:bg-white/90 hover:scale-105 transition-all shadow-sm text-slate-800"
                    >
                        {isPlaying ? (
                            <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor">
                                <rect x="2" y="2" width="3" height="12" rx="1" />
                                <rect x="9" y="2" width="3" height="12" rx="1" />
                            </svg>
                        ) : (
                            <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor" className="ml-1">
                                <path d="M2.5 1.5L12.5 8L2.5 14.5V1.5Z" />
                            </svg>
                        )}
                    </button>

                    {/* 进度条 */}
                    <div className="flex-1 flex flex-col gap-2 relative z-10">
                        <div className="relative h-2.5 bg-black/5 rounded-full overflow-hidden cursor-pointer shadow-inner border border-white/30"
                            onClick={handleProgressClick}
                        >
                            <div
                                ref={progressBarRef}
                                className="absolute top-0 left-0 h-full rounded-full transition-all duration-75"
                                style={{
                                    width: '0%',
                                    background: 'linear-gradient(90deg, #64748b, #334155)',
                                    boxShadow: '0 0 10px rgba(51, 65, 85, 0.3)'
                                }}
                            />
                        </div>
                        <div className="flex justify-between items-center text-[11px] font-black text-slate-600 tracking-wider" style={{ textShadow: '0 1px 1px rgba(255,255,255,0.8)' }}>
                            <div className="flex items-center gap-1.5">
                                <span ref={progressTextRef}>00:00:00</span>
                                <span className="text-slate-400 font-medium">/</span>
                                <span className="text-slate-500">{formatElapsed(timeRangeRef.current.max)}</span>
                            </div>
                        </div>
                    </div>

                    {/* 速度控制 */}
                    <div className="flex items-center gap-1.5 bg-white/30 p-1.5 rounded-full shadow-inner border border-white/50 relative z-10">
                        {[0.5, 1, 2, 1024].map(speed => (
                            <button
                                key={speed}
                                onClick={() => setAnimationSpeed(speed)}
                                className={`px-3 py-1.5 rounded-full text-xs font-black transition-all ${animationSpeed === speed
                                    ? 'bg-slate-700 text-white shadow-md'
                                    : 'text-slate-600 hover:text-slate-900 hover:bg-white/60'
                                    }`}
                            >
                                {speed}×
                            </button>
                        ))}
                    </div>

                    {/* 城市快速跳转 (Custom Dropdown) */}
                    <div className="flex items-center ml-2 relative z-50">
                        <div className="relative group">
                            {/* Dropdown Trigger */}
                            <button
                                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                                className="appearance-none bg-white/60 backdrop-blur-md text-slate-800 font-bold text-sm rounded-full border border-white/80 pl-5 pr-11 py-2 outline-none cursor-pointer hover:bg-white/80 transition-all shadow-sm focus:ring-2 focus:ring-slate-300 w-[140px] text-left flex items-center justify-between"
                            >
                                {CITIES.find(c => c.id === currentCity)?.label || "选择城市"}

                                <div className={`absolute right-3.5 pointer-events-none text-slate-500 transition-transform duration-300 ${isDropdownOpen ? 'rotate-180' : 'rotate-0'}`}>
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                        <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                </div>
                            </button>

                            {/* Dropdown Menu (Glassmorphism) */}
                            {isDropdownOpen && (
                                <>
                                    {/* Invisible backdrop to catch clicks outside */}
                                    <div
                                        className="fixed inset-0 z-40"
                                        onClick={() => setIsDropdownOpen(false)}
                                    ></div>

                                    <div className="absolute bottom-[130%] right-0 w-[140px] bg-white/70 backdrop-blur-xl border border-white/80 rounded-2xl shadow-[0_8px_32px_0_rgba(31,38,135,0.2)] py-2 z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
                                        {CITIES.map(city => (
                                            <div
                                                key={city.id}
                                                onClick={() => handleCityJump(city.id)}
                                                className={`px-5 py-2.5 text-sm font-semibold cursor-pointer transition-colors ${currentCity === city.id
                                                    ? 'bg-slate-800/10 text-slate-900 border-l-4 border-slate-700'
                                                    : 'text-slate-600 hover:bg-white/50 hover:text-slate-800 border-l-4 border-transparent'
                                                    }`}
                                            >
                                                {city.label}
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

/** 将秒数格式化为 HH:MM:SS */
function formatElapsed(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
