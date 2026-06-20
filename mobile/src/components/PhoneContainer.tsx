import React, { useState, useEffect } from 'react';
import { Smartphone, Battery, Wifi, ShieldCheck, Moon, Sun, Volume2, VolumeX, Sparkles } from 'lucide-react';

interface PhoneContainerProps {
  children: React.ReactNode;
  theme: 'dark' | 'light';
  setTheme: (t: 'dark' | 'light') => void;
}

export default function PhoneContainer({ children, theme, setTheme }: PhoneContainerProps) {
  const [time, setTime] = useState('');
  const [batteryLevel, setBatteryLevel] = useState(88);
  const [soundOn, setSoundOn] = useState(true);
  const [showIslandAlert, setShowIslandAlert] = useState(true);

  // Auto time update in status bar
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      let hours = now.getHours();
      const minutes = now.getMinutes().toString().padStart(2, '0');
      const ampm = hours >= 12 ? 'PM' : 'AM';
      hours = hours % 12 || 12;
      setTime(`${hours}:${minutes} ${ampm}`);
    };
    updateTime();
    const timer = setInterval(updateTime, 60000);
    return () => clearInterval(timer);
  }, []);

  // Slowly simulate discharging battery
  useEffect(() => {
    const interval = setInterval(() => {
      setBatteryLevel((prev) => (prev > 1 ? prev - 1 : 100));
    }, 120000);
    return () => clearInterval(interval);
  }, []);

  // Dynamic Island auto-hide notification
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowIslandAlert(false);
    }, 5500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="flex flex-col xl:flex-row items-center justify-center min-h-screen bg-[#050505] text-[#e2e8f0] p-3 sm:p-6 md:p-8 font-sans overflow-hidden relative">
      
      {/* Visual background ambient glow elements from High Density theme */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[45%] h-[45%] bg-blue-900/15 rounded-full blur-[140px]"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[45%] h-[45%] bg-purple-900/15 rounded-full blur-[140px]"></div>
      </div>

      {/* Left Column: Interactive Settings panel for the mockup (Show only on Desktop) */}
      <div className="hidden xl:flex flex-col max-w-sm mr-12 space-y-6 text-left shrink-0 select-none z-10">
        <div>
          <div className="inline-flex items-center space-x-2 px-3 py-1 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full text-xs font-semibold text-slate-100 uppercase tracking-widest leading-none mb-3 shadow-md">
            <Sparkles className="w-3 h-3 animate-pulse" />
            <span>High Density Console</span>
          </div>
          <h1 className="text-4xl font-extrabold text-white tracking-tight leading-tight">
            Agnes<span className="text-blue-500">AI</span> <br />
            <span className="text-slate-400 text-2xl font-normal tracking-wide">
              Control Interface
            </span>
          </h1>
          <p className="text-slate-500 text-xs mt-3 leading-relaxed">
            Welcome to the mobile interface of Agnes AI, optimized for real-time supervision of active image & video GPU synthesis workloads.
          </p>
        </div>

        {/* Simulator controls */}
        <div className="p-5 bg-[#161920] border border-white/5 rounded-3xl space-y-5 shadow-2xl backdrop-blur-md">
          <h3 className="font-semibold text-slate-400 text-[10px] uppercase tracking-wider">Device Simulator Settings</h3>
          
          <div className="space-y-3 text-sm">
            {/* Dark & Light toggle */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-2 text-xs">
                {theme === 'dark' ? <Moon className="w-4 h-4 text-blue-400" /> : <Sun className="w-4 h-4 text-amber-400" />}
                Theme Preset
              </span>
              <button 
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 active:scale-95 transition-all text-[11px] rounded-xl font-medium text-slate-200 border border-white/5"
              >
                {theme === 'dark' ? 'Switch Light' : 'Switch Dark'}
              </button>
            </div>

            {/* Sound Effects Toggle */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-2 text-xs">
                {soundOn ? <Volume2 className="w-4 h-4 text-emerald-400" /> : <VolumeX className="w-4 h-4 text-rose-400" />}
                Haptic Feedbacks
              </span>
              <button 
                onClick={() => setSoundOn(!soundOn)}
                className={`px-3 py-1 transition-all text-[11px] rounded-xl font-medium border border-white/5 ${
                  soundOn ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20' : 'bg-slate-800 text-slate-500'
                }`}
              >
                {soundOn ? 'Active' : 'Muted'}
              </button>
            </div>

            {/* Simulated Battery Level */}
            <div className="flex items-center justify-between">
              <span className="text-slate-400 flex items-center gap-2 text-xs">
                <Battery className="w-4 h-4 text-blue-400" />
                Battery Charge
              </span>
              <span className="text-[11px] font-mono font-bold text-slate-300 bg-slate-900 px-2 py-0.5 rounded-md border border-white/5">
                {batteryLevel}%
              </span>
            </div>

            {/* Developer credentials */}
            <div className="pt-2.5 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-500">
              <span className="flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />
                Network status
              </span>
              <span className="text-blue-400 font-mono text-[10px] font-semibold">● ACTIVE_SYNC</span>
            </div>
          </div>
        </div>

        {/* Tip */}
        <div className="p-4 bg-[#161920]/60 border border-white/5 rounded-2xl text-[11px] text-slate-400 leading-relaxed shadow-sm">
          💡 <span className="font-semibold text-white">Interactive Prompt Loop:</span> Generate deep synthesis seeds from the **AI Assistant** coach with one click.
        </div>
      </div>

      {/* Center: The Phone Mockup Frame wrapper with High Density border and background settings */}
      <div className="relative w-full max-w-[375px] sm:h-[760px] h-[100dvh] bg-[#0F1115] sm:rounded-[48px] border-[8px] border-[#1C1F26] shadow-2xl flex flex-col justify-between overflow-hidden z-20 shrink-0 outline-none
                  sm:ring-[1px] sm:ring-white/10 transition-all duration-300">
        
        {/* Phone Notch/Dynamic Island Speaker cutout (Desktop Only) */}
        <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-32 h-6 md:h-7 bg-black rounded-b-2xl z-50 flex items-center justify-center transition-all duration-300">
          
          {/* Animated Dynamic Island Alert bubble (Theme styling) */}
          {showIslandAlert ? (
            <div className="absolute top-1 w-[128%] h-5 md:h-6 bg-[#0F1115] border border-white/5 rounded-full flex items-center justify-between px-3 shadow-lg animate-pulse text-[8px] text-slate-200 font-bold tracking-tight">
              <span className="flex items-center gap-1 text-slate-200 uppercase tracking-wider text-[7px]">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-ping" />
                AGNES ACTIVE PIPELINE
              </span>
              <span className="text-blue-405 font-mono">240 T_UNITS</span>
            </div>
          ) : (
            <div className="w-10 h-1 bg-slate-700 rounded-full opacity-60" />
          )}
        </div>

        {/* Side physical buttons for detailing */}
        <div className="hidden sm:block absolute left-[-9px] top-28 w-[3px] h-10 bg-slate-800 rounded-l" />
        <div className="hidden sm:block absolute left-[-9px] top-44 w-[3px] h-14 bg-slate-800 rounded-l" />
        <div className="hidden sm:block absolute left-[-9px] top-60 w-[3px] h-14 bg-[#1C1F26] rounded-l" />
        <div className="hidden sm:block absolute right-[-9px] top-36 w-[3px] h-16 bg-slate-800 rounded-r" />

        {/* INNER PHONE CONTENT SCREEN CONTAINER */}
        <div className={`w-full h-full flex flex-col ${theme === 'dark' ? 'bg-[#0F1115] text-[#f1f5f9]' : 'bg-slate-50 text-slate-900'} relative overflow-hidden pt-6 rounded-[34px] sm:rounded-[38px]`}>
          
          {/* Top simulated status bar */}
          <div className="w-full h-6 px-6 flex items-center justify-between text-[10px] font-semibold select-none z-40 outline-none mt-1">
            <span className={theme === 'dark' ? 'text-slate-300 font-mono' : 'text-slate-800'}>{time}</span>
            <div className="flex items-center space-x-2">
              <Wifi className={`w-3 h-3 ${theme === 'dark' ? 'text-slate-400' : 'text-slate-700'}`} />
              <div className="flex items-center space-x-0.5">
                <span className={`text-[8.5px] font-mono mr-0.5 ${theme === 'dark' ? 'text-slate-500' : 'text-slate-500'}`}>{batteryLevel}%</span>
                <div className={`w-4 h-2 rounded-xs flex items-center ${theme === 'dark' ? 'bg-blue-500/20' : 'bg-slate-300'}`}>
                  <div className={`w-2.5 h-1.5 rounded-2xs ${batteryLevel > 20 ? 'bg-blue-400' : 'bg-rose-500'}`}></div>
                </div>
              </div>
            </div>
          </div>

          {/* Actual Client Sandbox Application Screen */}
          <div className="flex-1 overflow-hidden relative flex flex-col pt-0.5">
            {children}
          </div>

          {/* Simulated Home Swipe Indicator bottom center bar */}
          <div className="w-full h-4 flex items-center justify-center select-none bg-transparent shrink-0">
            <div className={`w-24 h-1 rounded-full ${theme === 'dark' ? 'bg-slate-800' : 'bg-slate-300'} mb-1 opacity-80`} />
          </div>
        </div>
      </div>

      {/* Right Column: High Density theme annotation notes (Exactly from user Design HTML) */}
      <div className="hidden xl:flex flex-col w-64 ml-12 space-y-6 text-left shrink-0 z-10 select-none">
        <div className="p-4 border-l-2 border-blue-500 bg-blue-500/5 rounded-r-xl">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-blue-400 mb-1.5">Mobile Viewport</h4>
          <p className="text-xs text-slate-400 leading-relaxed italic">
            "Agnes AI provides a high-density, real-time dashboard optimized for mobile supervision of autonomous agents."
          </p>
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-blue-500"></div>
            <span className="text-xs text-slate-300">Adaptive Dark interface</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-purple-500"></div>
            <span className="text-xs text-slate-300">Multi-Model Orchestration</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
            <span className="text-xs text-slate-300">Real-time Status Sync</span>
          </div>
        </div>
      </div>

    </div>
  );
}
