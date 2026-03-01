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
const ANIMATION_SPEED = 60; // 每帧推进60秒（数据覆盖3.5天）
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
            radius: 35,
            extruded: true,
            pickable: true,
            elevationScale: 1,
            getPosition: (d: any) => d.geometry.coordinates,
            getFillColor: [239, 68, 68, 160], // 对应面状的柔和红
            getLineColor: [185, 28, 28, 200],
            getElevation: 80,
        }),
    ], [buildingsData, poiDemand, poiSensitive, sensitivePoints]);

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
    const layers = useMemo(() =>
        [...staticLayers, tripsLayer].filter(Boolean),
        [staticLayers, tripsLayer]
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
        <div className="absolute inset-0 z-0" style={{ background: '#f0f0f0' }}>
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

            {/* 底部动画控制条 */}
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 pointer-events-auto">
                <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-700/60 rounded-2xl px-6 py-4 flex items-center gap-5 shadow-2xl min-w-[520px]">
                    {/* 播放/暂停按钮 */}
                    <button
                        onClick={() => setIsPlaying(!isPlaying)}
                        className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-400 to-emerald-400 flex items-center justify-center hover:scale-110 transition-transform shadow-lg shadow-cyan-500/30"
                    >
                        {isPlaying ? (
                            <svg width="14" height="16" viewBox="0 0 14 16" fill="none">
                                <rect x="1" y="1" width="4" height="14" rx="1" fill="#0f172a" />
                                <rect x="9" y="1" width="4" height="14" rx="1" fill="#0f172a" />
                            </svg>
                        ) : (
                            <svg width="14" height="16" viewBox="0 0 14 16" fill="none">
                                <path d="M2 1L13 8L2 15V1Z" fill="#0f172a" />
                            </svg>
                        )}
                    </button>

                    {/* 进度条 */}
                    <div className="flex-1 flex flex-col gap-1.5">
                        <div className="relative h-2 bg-slate-800 rounded-full overflow-hidden cursor-pointer"
                            onClick={handleProgressClick}
                        >
                            <div
                                ref={progressBarRef}
                                className="absolute top-0 left-0 h-full rounded-full"
                                style={{
                                    width: '0%',
                                    background: 'linear-gradient(90deg, #06b6d4, #10b981, #22d3ee)',
                                    boxShadow: '0 0 12px rgba(6, 182, 212, 0.6)',
                                }}
                            />
                        </div>
                        <div className="flex justify-between text-[10px] font-mono text-slate-500">
                            <span ref={progressTextRef}>00:00:00</span>
                            <span>{formatElapsed(timeRangeRef.current.max)}</span>
                        </div>
                    </div>

                    {/* 速度控制 */}
                    <div className="flex items-center gap-2">
                        {[0.5, 1, 2, 4].map(speed => (
                            <button
                                key={speed}
                                onClick={() => setAnimationSpeed(speed)}
                                className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold transition-all ${animationSpeed === speed
                                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
                                    : 'text-slate-500 hover:text-slate-300 border border-transparent'
                                    }`}
                            >
                                {speed}×
                            </button>
                        ))}
                    </div>

                    {/* 城市快速跳转 (仅跳转视角) */}
                    <div className="flex items-center gap-2 ml-4 border-l border-slate-700/60 pl-4">
                        <select
                            value={currentCity}
                            onChange={handleCityJump}
                            className="bg-slate-800 text-cyan-300 text-sm rounded border border-slate-600 px-2 py-1 outline-none cursor-pointer"
                        >
                            <option value="shenzhen">深圳南山</option>
                            <option value="beijing">北京核心</option>
                            <option value="shanghai">上海核心</option>
                            <option value="guangzhou">广州核心</option>
                            <option value="chengdu">成都核心</option>
                            <option value="chongqing">重庆主城</option>
                        </select>
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
