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
const ANIMATION_SPEED = 0.5; // 每帧推进 0.5 秒，大幅度降低以模拟真实飞行速度
const TRAIL_LENGTH = 1200;  // 拖尾长度（秒），越长拖尾越明显

export default function MapContainer() {
    // ====== 策略一：按需加载 + 缓存 ======
    // 只存储当前城市的数据，不再一次性加载全部
    const [buildingsData, setBuildingsData] = useState<any>(null);
    const [poiDemand, setPoiDemand] = useState<any>(null);
    const [poiSensitive, setPoiSensitive] = useState<any>(null);
    const [trajectories, setTrajectories] = useState<UAVPath[]>([]);
    const [isLoadingCity, setIsLoadingCity] = useState(false);

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
    // DeckGL 实例 ref，用于直接更新 layer props
    const deckRef = useRef<any>(null);
    // 进度条 DOM ref，用于直接操作 DOM 避免重渲染
    const progressBarRef = useRef<HTMLDivElement>(null);
    const progressTextRef = useRef<HTMLSpanElement>(null);

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
            const [bRes, pDRes, pSRes] = await Promise.all([
                fetch(`${basePath}/buildings_3d.geojson`).then(r => r.ok ? r.json() : null),
                fetch(`${basePath}/poi_demand.geojson`).then(r => r.ok ? r.json() : null),
                fetch(`${basePath}/poi_sensitive.geojson`).then(r => r.ok ? r.json() : null)
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

        // 加载轨迹数据
        (async () => {
            try {
                const tRes = await fetch('/data/processed/trajectories/uav_trajectories.json');
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

        animFrameRef.current = requestAnimationFrame(animate);
    }, [animationSpeed]);

    useEffect(() => {
        if (isPlaying) {
            animFrameRef.current = requestAnimationFrame(animate);
        }
        return () => {
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        };
    }, [isPlaying, animate]);

    // 城市切换处理：切换视角 + 按需加载数据
    const handleCityJump = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
        const city = e.target.value;
        setCurrentCity(city);
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
            getColor: [255, 180, 0],        // 金黄色
            widthMinPixels: 2.5,
            trailLength: TRAIL_LENGTH,
            currentTime: currentTimeRef.current,
            shadowEnabled: false,
            opacity: 0.9,
        }),
        [trajectories]
    );

    // 合并所有 layers
    // 拖拽地图时会触发 setViewState 引起 React 重新渲染
    // 在重新渲染时必须使用实时最新的 currentTime 来 clone 轨迹图层，否则 DeckGL 会回退到旧时间导致轨迹“消失”
    const layers = useMemo(() =>
        [...staticLayers, tripsLayer ? tripsLayer.clone({ currentTime: currentTimeRef.current }) : undefined].filter(Boolean),
        [staticLayers, tripsLayer, viewState]
    );

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
                <div className="bg-white/40 backdrop-blur-2xl border border-white/50 rounded-[2rem] px-8 py-5 flex items-center gap-6 shadow-[0_8px_32px_0_rgba(31,38,135,0.15)] min-w-[580px] relative overflow-hidden">
                    {/* 微弱暗色渐变垫底 */}
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-900/5 to-transparent pointer-events-none"></div>

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
                        <div className="flex justify-between text-[11px] font-black text-slate-600 tracking-wide" style={{ textShadow: '0 1px 1px rgba(255,255,255,0.8)' }}>
                            <span ref={progressTextRef}>00:00:00</span>
                            <span>{formatElapsed(timeRangeRef.current.max)}</span>
                        </div>
                    </div>

                    {/* 速度控制 */}
                    <div className="flex items-center gap-1.5 bg-white/30 p-1.5 rounded-full shadow-inner border border-white/50 relative z-10">
                        {[0.5, 1, 2, 4].map(speed => (
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

                    {/* 城市快速跳转 */}
                    <div className="flex items-center ml-2 relative z-10">
                        <div className="relative group">
                            <select
                                value={currentCity}
                                onChange={handleCityJump}
                                className="appearance-none bg-white/60 backdrop-blur-md text-slate-800 font-bold text-sm rounded-full border border-white/80 pl-5 pr-11 py-2 outline-none cursor-pointer hover:bg-white/80 transition-all shadow-sm focus:ring-2 focus:ring-slate-300"
                            >
                                <option value="shenzhen" className="font-medium bg-white text-slate-800">深圳 · 南山</option>
                                <option value="beijing" className="font-medium bg-white text-slate-800">北京 · 核心</option>
                                <option value="shanghai" className="font-medium bg-white text-slate-800">上海 · 核心</option>
                                <option value="guangzhou" className="font-medium bg-white text-slate-800">广州 · 核心</option>
                                <option value="chengdu" className="font-medium bg-white text-slate-800">成都 · 核心</option>
                                <option value="chongqing" className="font-medium bg-white text-slate-800">重庆 · 主城</option>
                            </select>
                            {/* Custom Select Arrow */}
                            <div className="absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500 group-hover:text-slate-800 transition-colors">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                            </div>
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
