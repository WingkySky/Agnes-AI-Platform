import React, { useState } from 'react';
import { User, Coins, Crown, Zap, ShieldAlert, BadgeCheck, Check, HelpCircle, ChevronRight, Sliders, Settings } from 'lucide-react';

interface ProfileTabProps {
  userCredits: number;
  setUserCredits: React.Dispatch<React.SetStateAction<number>>;
  theme: 'dark' | 'light';
}

export default function ProfileTab({ userCredits, setUserCredits, theme }: ProfileTabProps) {
  const [hasCheckedIn, setHasCheckedIn] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [profileNotification, setProfileNotification] = useState<string | null>(null);

  const handleDailyCheckIn = () => {
    if (hasCheckedIn) return;
    setUserCredits((prev) => prev + 50);
    setHasCheckedIn(true);
    setSuccessMsg('Checked in! Received +50 Agnes Credits.');
    setTimeout(() => setSuccessMsg(''), 4000);
  };

  const triggerBillingAction = (planName: string) => {
    setProfileNotification(`BIllING PRE-FLIGHT AUTHENTICATION SUCCESSFUL FOR [${planName.toUpperCase()}]`);
    setTimeout(() => setProfileNotification(null), 3500);
  };

  return (
    <div id="profile-tab" className="h-full flex flex-col pt-2 overflow-hidden select-none text-left relative">
      
      {/* Header title (High Density Theme compliance) */}
      <div className="px-4 pb-2 border-b border-white/5 shrink-0 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)] flex shrink-0"></span>
            Agnes<span className="text-blue-500">AI</span>
            <span className="text-[10px] text-slate-500 font-mono font-normal ml-0.5">/ PORTAL</span>
          </h2>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">Account status & billing modules</p>
        </div>

        {/* Global gear Settings */}
        <div className="w-6 h-6 rounded bg-[#161920] border border-white/5 flex items-center justify-center cursor-pointer hover:border-slate-500">
          <Settings className="w-3 h-3 text-slate-400" />
        </div>
      </div>

      {/* Floating profile notification card */}
      {profileNotification && (
        <div className="absolute top-12 left-4 right-4 z-50 bg-emerald-500 text-slate-950 px-3 py-2 rounded-xl border border-emerald-400/20 text-[8px] font-mono tracking-wider font-bold text-center animate-bounce shadow-xl flex items-center justify-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-950 animate-ping" />
          {profileNotification}
        </div>
      )}

      {/* Main Account details scrolling viewport */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-none">
        
        {/* User Card */}
        <div className="p-3 bg-[#161920] border border-white/5 rounded-xl flex items-center space-x-3 relative shadow-xl shrink-0">
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80"
            alt="my-avatar"
            className="w-11 h-11 rounded-full object-cover border border-blue-500/30"
          />
          <div>
            <div className="flex items-center space-x-1">
              <span className="text-[11px] font-black text-slate-50 tracking-wide font-mono">AGNES_CREATOR_X</span>
              <BadgeCheck className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <p className="text-[8px] text-slate-500 font-mono">ACCOUNT UID: #4928109-AG</p>
            <span className="inline-block mt-1 px-1.5 py-0.5 bg-blue-500/10 border border-blue-500/20 text-blue-400 font-extrabold text-[7.5px] uppercase tracking-wider rounded">
              👑 Agnes VIP Level II
            </span>
          </div>

          <div className="absolute top-2.5 right-2.5 flex items-center bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.2 rounded text-[7.5px] text-blue-400 font-black font-mono">
            PRO TIERS
          </div>
        </div>

        {/* Credits Panel */}
        <div className="p-3 bg-[#161920] border border-white/5 rounded-xl space-y-3">
          <div className="flex justify-between items-center text-left">
            <div>
              <span className="text-[7.5px] font-bold text-slate-500 uppercase tracking-widest block font-mono">Agnes GPU Balance</span>
              <p className="text-base font-black text-slate-50 font-mono mt-0.5 flex items-center gap-1.5">
                <Coins className="w-4 h-4 text-blue-400" />
                {userCredits} <span className="text-[9px] text-slate-550 lowercase font-sans">Units ready</span>
              </p>
            </div>

            {/* Check-In Action Button */}
            <button
              onClick={handleDailyCheckIn}
              disabled={hasCheckedIn}
              className={`px-3 py-1.5 text-[9px] font-extrabold rounded-lg transition-all uppercase ${
                hasCheckedIn
                  ? 'bg-emerald-500/5 border border-emerald-500/10 text-emerald-500 cursor-not-allowed'
                  : 'bg-blue-500 text-slate-950 hover:scale-[1.01] active:scale-[0.99] shadow-[0_0_8px_rgba(59,130,246,0.25)]'
              }`}
            >
              {hasCheckedIn ? 'Checked ✔' : 'Daily Check-In (+50)'}
            </button>
          </div>

          {/* Progress balance visually */}
          <div className="space-y-1">
            <div className="w-full bg-[#0F1115] h-1 rounded-full overflow-hidden border border-white/5">
              <div 
                className="bg-blue-500 h-full rounded-full transition-all duration-500" 
                style={{ width: `${Math.min((userCredits / 1000) * 100, 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[7px] font-bold font-mono text-slate-550">
              <span>0 CREDITS</span>
              <span>1000 MAX COMPUTE RATE</span>
            </div>
          </div>

          {/* Success messages for checking in */}
          {successMsg && (
            <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold text-[8.5px] tracking-wider text-center rounded-lg animate-fade-in font-mono uppercase">
              {successMsg}
            </div>
          )}
        </div>

        {/* Multi tier Creator status metrics */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 bg-[#161920] rounded-xl border border-white/5 text-center">
            <span className="text-[7.5px] font-bold uppercase text-slate-550 block font-mono mb-0.5">Renderings</span>
            <span className="text-xs font-black font-mono text-slate-200">24</span>
          </div>
          <div className="p-2 bg-[#161920] rounded-xl border border-white/5 text-center">
            <span className="text-[7.5px] font-bold uppercase text-slate-550 block font-mono mb-0.5">Likes</span>
            <span className="text-xs font-black font-mono text-blue-450">142</span>
          </div>
          <div className="p-2 bg-[#161920] rounded-xl border border-white/5 text-center">
            <span className="text-[7.5px] font-bold uppercase text-slate-550 block font-mono mb-0.5">Compute Hrs</span>
            <span className="text-xs font-black font-mono text-slate-200">3.4 h</span>
          </div>
        </div>

        {/* Upgrade Premium Tier plans showcase */}
        <div className="space-y-2 select-none text-left">
          <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest block font-mono px-0.5">VIP Subscription Plans</span>
          
          <div className="space-y-2">
            
            {/* Creator Plan */}
            <div className="p-2.5 bg-[#161920] border border-white/5 rounded-xl flex justify-between items-center">
              <div>
                <h4 className="text-[10px] font-bold text-slate-200 flex items-center gap-1.5 uppercase font-mono">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  Creator Premium
                </h4>
                <p className="text-[8px] text-slate-500 mt-0.5">3,000 Credits/mo • HQ Parallel synthesis</p>
              </div>
              <button 
                type="button"
                onClick={() => triggerBillingAction("Creator Premium")}
                className="px-2.5 py-1 bg-slate-950 text-slate-350 hover:text-slate-100 text-[9px] font-mono font-bold rounded border border-white/5 transition-all"
              >
                $9.90/MO
              </button>
            </div>

            {/* Pro Plan */}
            <div className="p-2.5 bg-[#161920] border border-blue-500/25 rounded-xl flex justify-between items-center relative">
              <div>
                <h4 className="text-[10px] font-bold text-slate-100 flex items-center gap-1.5 uppercase font-mono">
                  <Crown className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
                  Studio Developer
                </h4>
                <p className="text-[8px] text-slate-500 mt-0.5">Unlimited high-tier speeds • Dedicated API keys</p>
              </div>
              <button 
                type="button"
                onClick={() => triggerBillingAction("Studio Developer")}
                className="px-2.5 py-1 bg-blue-500 text-slate-950 text-[9px] font-bold uppercase rounded hover:scale-[1.01] active:scale-[0.99] transition-all shadow-[0_0_8px_rgba(59,130,246,0.3)]"
              >
                $29.00/MO
              </button>
            </div>

          </div>
        </div>

        {/* Configuration preferences */}
        <div className="p-2.5 bg-[#161920] border border-white/5 rounded-xl text-left space-y-2 text-[10.5px]">
          <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest block font-mono">System Preferences</span>
          
          <div className="flex items-center justify-between py-1 border-b border-slate-950 text-slate-350">
            <span>Double scale render resolution</span>
            <span className="text-[8.5px] font-bold text-emerald-400 font-mono">YES (AUTO)</span>
          </div>

          <div className="flex items-center justify-between py-1 border-b border-slate-950 text-slate-355">
            <span>Cloud computing regional node</span>
            <span className="text-[8.5px] font-bold text-slate-500 font-mono">SINGAPORE-HQ-AWS</span>
          </div>

          <div className="flex items-center justify-between py-1 text-slate-355">
            <span>Local file download target</span>
            <span className="text-[8.5px] font-bold text-slate-500 font-mono">CAMERA-GALLERY</span>
          </div>
        </div>

      </div>
    </div>
  );
}
