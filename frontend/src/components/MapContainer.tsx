import { useState, useEffect, useCallback, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { Map, type MapRef } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

const INITIAL_VIEW_STATE = {
    longitude: 113.935,
    latitude: 22.535,
    zoom: 13,
    pitch: 50,
    bearing: 15
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

// 预处理JSON的数据结构
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

    // 加载数据
    useEffect(() => {
        // 构建不同城市的数据路径
        const basePath = `/data/processed/${currentCity}`;

        // 重置数据，展现加载状态
        setBuildingsData(null);
        setPoiDemand(null);
        setPoiSensitive(null);

        fetch(`${basePath}/buildings_3d.geojson`).then(res => res.ok ? res.json() : null).then(setBuildingsData);
        fetch(`${basePath}/poi_demand.geojson`).then(res => res.ok ? res.json() : null).then(setPoiDemand);
        fetch(`${basePath}/poi_sensitive.geojson`).then(res => res.ok ? res.json() : null).then(setPoiSensitive);

        // 如果是深圳，加载轨迹数据
        if (currentCity === "shenzhen") {
            fetch('/data/processed/trajectories/uav_trajectories.json')
                .then(res => res.json())
                .then((data: PreprocessedData) => {
                    timeRangeRef.current = data.timeRange;
                    setTrajectories(data.trajectories);
                    setCurrentTime(0);
                    console.log(`✅ ${currentCity} 轨迹加载完成: ${data.sampledFlights}/${data.totalFlights} 条 (确定性采样)`);
                }).catch(() => {
                    setTrajectories([]);
                    timeRangeRef.current = { min: 0, max: 0 };
                });
        } else {
            setTrajectories([]);
            timeRangeRef.current = { min: 0, max: 0 };
        }

        // 更新视图中心
        if (CITY_COORDS[currentCity]) {
            setViewState(prev => ({
                ...prev,
                longitude: CITY_COORDS[currentCity].longitude,
                latitude: CITY_COORDS[currentCity].latitude,
            }));
        }

    }, [currentCity]);

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

        // 3D建筑层 - 暖灰色搭配白色底图
        new GeoJsonLayer({
            id: 'buildings-layer',
            data: buildingsData,
            extruded: true,
            getFillColor: [160, 170, 185, 230],       // 冷灰蓝色
            getLineColor: [120, 135, 155, 180],       // 边缘线
            lineWidthMinPixels: 1,
            getElevation: ((d: any) => d.properties.height || 20) as any,
            pickable: true,
            autoHighlight: true,
            highlightColor: [80, 140, 220, 255],
        }),

        // POI需求点 - 翡翠绿能量柱
        new GeoJsonLayer({
            id: 'poi-demand-layer',
            data: poiDemand,
            extruded: true,
            getElevation: 50,
            pointRadiusMinPixels: 4,
            pointRadiusMaxPixels: 20,
            getPointRadius: 30,
            getFillColor: [16, 185, 129, 200],
            pickable: true,
        }),

        // POI敏感区 - 暴击红禁飞柱
        new GeoJsonLayer({
            id: 'poi-sensitive-layer',
            data: poiSensitive,
            extruded: true,
            getElevation: 80,
            pointRadiusMinPixels: 4,
            pointRadiusMaxPixels: 20,
            getPointRadius: 40,
            getFillColor: [225, 29, 72, 200],
            pickable: true,
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
                controller={true}
                layers={layers}
                onViewStateChange={({ viewState }) => {
                    const { longitude, latitude, zoom, pitch, bearing } = viewState as any;
                    setViewState({ longitude, latitude, zoom, pitch, bearing });
                }}
            >
                <Map
                    ref={mapRef}
                    mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
                    reuseMaps
                    onLoad={handleMapLoad}
                />
            </DeckGL>

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

                    {/* 城市切换 */}
                    <div className="flex items-center gap-2 ml-4 border-l border-slate-700/60 pl-4">
                        <select
                            value={currentCity}
                            onChange={(e) => setCurrentCity(e.target.value)}
                            className="bg-slate-800 text-cyan-300 text-sm rounded border border-slate-600 px-2 py-1 outline-none"
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
