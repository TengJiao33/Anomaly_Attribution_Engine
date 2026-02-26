import { useState, useEffect, useCallback, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ColumnLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { Map, type MapRef } from 'react-map-gl/maplibre';
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

// 动画配置
const ANIMATION_SPEED = 60; // 每帧推进60秒（数据覆盖3.5天）
const TRAIL_LENGTH = 1200;  // 拖尾长度（秒），越长拖尾越明显

export default function MapContainer() {
    const [buildingsData, setBuildingsData] = useState<any>(null);
    const [poiDemand, setPoiDemand] = useState<any>(null);
    const [poiSensitive, setPoiSensitive] = useState<any>(null);
    const [trajectories, setTrajectories] = useState<UAVPath[]>([]);

    // 动画状态
    const [currentTime, setCurrentTime] = useState(0);
    const [isPlaying, setIsPlaying] = useState(true);
    const [animationSpeed, setAnimationSpeed] = useState(1);
    const timeRangeRef = useRef({ min: 0, max: 0 });
    const animFrameRef = useRef<number>(0);
    const mapRef = useRef<MapRef>(null);

    const [currentCity, setCurrentCity] = useState("shenzhen");
    const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

    // 一次性加载所有城市数据
    useEffect(() => {
        const loadAllData = async () => {
            const allBuildings: any[] = [];
            const allPoiDemand: any[] = [];
            const allPoiSensitive: any[] = [];

            await Promise.all(Object.keys(CITY_COORDS).map(async (city) => {
                const basePath = `/data/processed/${city}`;
                try {
                    const [bRes, pDRes, pSRes] = await Promise.all([
                        fetch(`${basePath}/buildings_3d.geojson`).then(r => r.ok ? r.json() : null),
                        fetch(`${basePath}/poi_demand.geojson`).then(r => r.ok ? r.json() : null),
                        fetch(`${basePath}/poi_sensitive.geojson`).then(r => r.ok ? r.json() : null)
                    ]);
                    if (bRes && bRes.features) allBuildings.push(...bRes.features);
                    if (pDRes && pDRes.features) allPoiDemand.push(...pDRes.features);
                    if (pSRes && pSRes.features) allPoiSensitive.push(...pSRes.features);
                } catch (e) {
                    console.error(`Failed to load data for ${city}`, e);
                }
            }));

            // 合并为大 FeatureCollection
            setBuildingsData({ type: 'FeatureCollection', features: allBuildings });
            setPoiDemand({ type: 'FeatureCollection', features: allPoiDemand });
            setPoiSensitive({ type: 'FeatureCollection', features: allPoiSensitive });

            // 加载深圳轨迹数据
            try {
                const tRes = await fetch('/data/processed/trajectories/uav_trajectories.json');
                if (tRes.ok) {
                    const data: PreprocessedData = await tRes.json();
                    timeRangeRef.current = data.timeRange;
                    setTrajectories(data.trajectories);
                    setCurrentTime(0);
                }
            } catch (e) {
                console.error("Failed to load trajectories", e);
            }
        };

        loadAllData();
    }, []);

    // 动画循环
    const animate = useCallback(() => {
        if (timeRangeRef.current.max === 0) {
            animFrameRef.current = requestAnimationFrame(animate);
            return;
        }

        setCurrentTime(prev => {
            const next = prev + ANIMATION_SPEED * animationSpeed;
            // 循环播放
            if (next > timeRangeRef.current.max) return 0;
            return next;
        });

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

    // 进度百分比
    const progress = timeRangeRef.current.max > 0 ? (currentTime / timeRangeRef.current.max) * 100 : 0;

    // 城市切换处理
    const handleCityJump = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const city = e.target.value;
        setCurrentCity(city);
        if (CITY_COORDS[city]) {
            setViewState(prev => ({
                ...prev,
                longitude: CITY_COORDS[city].longitude,
                latitude: CITY_COORDS[city].latitude,
            }));
        }
    };

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

    const layers: any[] = [
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
            data: poiSensitive?.features?.filter((f: any) => f.geometry.type === 'Point') || [],
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

        // 🔥 核心升级：TripsLayer 动态金黄拖尾轨迹
        new TripsLayer({
            id: 'uav-trips-layer',
            data: trajectories,
            getPath: (d: UAVPath) => d.path,
            getTimestamps: (d: UAVPath) => d.timestamps,
            getColor: [255, 180, 0],        // 金黄色
            widthMinPixels: 2.5,
            trailLength: TRAIL_LENGTH,
            currentTime: currentTime,
            shadowEnabled: false,
            opacity: 0.9,
        }),
    ].filter(Boolean);

    return (
        <div className="absolute inset-0 z-0" style={{ background: '#f0f0f0' }}>
            <DeckGL
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
                onViewStateChange={({ viewState }) => {
                    const { longitude, latitude, zoom, pitch, bearing } = viewState as any;
                    setViewState({ longitude, latitude, zoom, pitch, bearing, maxPitch: INITIAL_VIEW_STATE.maxPitch });
                }}
            >
                <Map
                    ref={mapRef}
                    mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
                    reuseMaps
                    onLoad={handleMapLoad}
                    maxPitch={INITIAL_VIEW_STATE.maxPitch}
                />
            </DeckGL>

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
                            onClick={(e) => {
                                const rect = e.currentTarget.getBoundingClientRect();
                                const pct = (e.clientX - rect.left) / rect.width;
                                setCurrentTime(pct * timeRangeRef.current.max);
                            }}
                        >
                            <div
                                className="absolute top-0 left-0 h-full rounded-full transition-[width] duration-75"
                                style={{
                                    width: `${progress}%`,
                                    background: 'linear-gradient(90deg, #06b6d4, #10b981, #22d3ee)',
                                    boxShadow: '0 0 12px rgba(6, 182, 212, 0.6)',
                                }}
                            />
                        </div>
                        <div className="flex justify-between text-[10px] font-mono text-slate-500">
                            <span>{formatElapsed(currentTime)}</span>
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
