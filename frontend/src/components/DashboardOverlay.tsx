import { Activity, ShieldAlert, Package, Navigation, Zap } from 'lucide-react';

export default function DashboardOverlay() {
    return (
        <div className="absolute top-0 left-0 w-full h-full pointer-events-none z-10 flex flex-col justify-between p-6">
            {/* Top Bar */}
            <div className="flex justify-between items-start pointer-events-auto">
                <div className="bg-slate-900/80 backdrop-blur-md border border-slate-700/50 p-6 rounded-2xl shadow-2xl flex flex-col gap-2 min-w-[320px]">
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-emerald-400 to-sky-400 bg-clip-text text-transparent">
                        城市低空物流监控平台
                    </h1>
                    <p className="text-slate-400 text-sm font-medium tracking-wide">
                        深圳南山运营控制中心
                    </p>

                    <div className="mt-4 flex flex-col gap-3">
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400 text-sm flex items-center gap-2"><Navigation size={16} /> 活跃无人机</span>
                            <span className="text-emerald-400 font-mono text-xl font-bold">142</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400 text-sm flex items-center gap-2"><Package size={16} /> 今日配送单量</span>
                            <span className="text-slate-200 font-mono text-xl font-bold">1,894</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400 text-sm flex items-center gap-2"><Activity size={16} /> 网络空域负载</span>
                            <span className="text-amber-400 font-mono text-xl font-bold">84%</span>
                        </div>
                    </div>
                </div>

                {/* Status Indicators */}
                <div className="bg-slate-900/80 backdrop-blur-md border border-slate-700/50 px-4 py-3 rounded-xl flex items-center gap-4 shadow-xl">
                    <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.5)]"></div>
                        <span className="text-sm font-medium text-slate-300">系统运行正常</span>
                    </div>
                    <div className="h-4 w-px bg-slate-700"></div>
                    <div className="flex items-center gap-2 text-slate-400 text-sm">
                        <Zap size={14} className="text-sky-400" />
                        <span>遥测信号: 实时</span>
                    </div>
                </div>
            </div>

            {/* Bottom Panel */}
            <div className="pointer-events-auto self-end w-[400px]">
                <div className="bg-slate-900/80 backdrop-blur-md border border-slate-700/50 p-5 rounded-2xl shadow-2xl">
                    <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <ShieldAlert size={16} className="text-rose-400" />
                        事件监控中心
                    </h3>
                    <div className="flex flex-col gap-3">
                        <div className="bg-slate-800/50 rounded-lg p-3 border-l-2 border-rose-500 hover:bg-slate-800/80 transition-colors cursor-pointer">
                            <div className="flex justify-between items-start mb-1">
                                <span className="text-xs font-mono text-rose-400 font-bold">ALE-101</span>
                                <span className="text-xs text-slate-500">1分钟前</span>
                            </div>
                            <p className="text-sm text-slate-300 font-medium">防撞预警: 接近深圳医院 (禁飞区)</p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3 border-l-2 border-amber-500 hover:bg-slate-800/80 transition-colors cursor-pointer">
                            <div className="flex justify-between items-start mb-1">
                                <span className="text-xs font-mono text-amber-400 font-bold">WRN-402</span>
                                <span className="text-xs text-slate-500">5分钟前</span>
                            </div>
                            <p className="text-sm text-slate-300 font-medium">气象警报: 总部枢纽检测到强烈风切变</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
