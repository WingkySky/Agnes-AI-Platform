import React, { useState } from 'react';
import { Play, Download, Trash2, Clock, Sparkles, FolderHeart, Image, Film, Copy, Check, Eye } from 'lucide-react';
import { GenerationJob } from '../types';

interface CreationsTabProps {
  jobs: GenerationJob[];
  setJobs: React.Dispatch<React.SetStateAction<GenerationJob[]>>;
  theme: 'dark' | 'light';
}

export default function CreationsTab({ jobs, setJobs, theme }: CreationsTabProps) {
  const [activeFilter, setActiveFilter] = useState<'all' | 'image' | 'video'>('all');
  const [selectedJob, setSelectedJob] = useState<GenerationJob | null>(null);
  const [copied, setCopied] = useState(false);
  const [downloadNotification, setDownloadNotification] = useState<string | null>(null);

  // Filter personal portfolio jobs list
  const filteredJobs = jobs.filter((job) => {
    if (activeFilter === 'all') return true;
    return job.type === activeFilter;
  });

  const handleDeleteJob = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setJobs((prev) => prev.filter((job) => job.id !== id));
    if (selectedJob && selectedJob.id === id) {
      setSelectedJob(null);
    }
  };

  const handleCopyPrompt = (prompt: string) => {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const triggerExportNotification = () => {
    setDownloadNotification("RAW ORIGINAL HQ ASSET EXPORTED SUCCESSFULLY");
    setTimeout(() => setDownloadNotification(null), 3000);
  };

  return (
    <div id="creations-tab" className="h-full flex flex-col pt-2 overflow-hidden select-none text-left">
      
      {/* View Header (High Density Theme compliance) */}
      <div className="px-4 pb-2 border-b border-white/5 flex justify-between items-center shrink-0 mt-1">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded bg-pink-500 shadow-[0_0_8px_rgba(236,72,153,0.5)] flex shrink-0"></span>
            Agnes<span className="text-blue-500">AI</span>
            <span className="text-[10px] text-slate-500 font-mono font-normal ml-0.5">/ PORTFOLIO</span>
          </h2>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">Synchronized Render Archives</p>
        </div>

        {/* Total Assets Balance indicators */}
        <div className="text-[8px] font-mono text-slate-400 bg-[#161920] border border-white/5 px-2.5 py-0.5 rounded-md font-bold">
          {jobs.length} WORK UNITS
        </div>
      </div>

      {/* Categories Filter tab */}
      <div className="px-4 py-1.5 flex items-center space-x-1 border-b border-white/5 shrink-0 bg-[#0F1115]">
        <button
          onClick={() => setActiveFilter('all')}
          className={`flex-1 py-1 text-center text-[9px] font-bold uppercase rounded-lg transition-all ${
            activeFilter === 'all'
              ? 'bg-blue-500 text-slate-950 font-extrabold shadow-[0_0_8px_rgba(59,130,246,0.355)]'
              : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          Σ ALL
        </button>
        <button
          onClick={() => setActiveFilter('image')}
          className={`flex-1 py-1 text-center text-[9px] font-bold uppercase rounded-lg flex items-center justify-center gap-1 transition-all ${
            activeFilter === 'image'
              ? 'bg-blue-500 text-slate-950 font-extrabold shadow-[0_0_8px_rgba(59,130,246,0.355)]'
              : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Image className="w-2.5 h-2.5" />
          STILLS
        </button>
        <button
          onClick={() => setActiveFilter('video')}
          className={`flex-1 py-1 text-center text-[9px] font-bold uppercase rounded-lg flex items-center justify-center gap-1 transition-all ${
            activeFilter === 'video'
              ? 'bg-blue-500 text-slate-950 font-extrabold shadow-[0_0_8px_rgba(59,130,246,0.355)]'
              : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Film className="w-2.5 h-2.5" />
          CLIPS
        </button>
      </div>

      {/* Custom float toast notifier */}
      {downloadNotification && (
        <div className="absolute top-12 left-4 right-4 z-55 bg-emerald-500 text-slate-950 px-3 py-2 rounded-xl border border-emerald-450/30 text-[8.5px] font-mono font-bold tracking-wider text-center animate-bounce shadow-xl flex items-center justify-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-950 animate-ping" />
          {downloadNotification}
        </div>
      )}
      {/* Main Creations Grid space */}
      <div className="flex-1 overflow-y-auto p-4 scrollbar-none">
        {filteredJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
            <div className="w-12 h-12 rounded-xl bg-[#161920] border border-white/5 flex items-center justify-center">
              <FolderHeart className="w-5 h-5 text-slate-550" />
            </div>
            <div>
              <p className="text-[10px] font-mono text-slate-400 font-bold uppercase">NO TELEMETRY RECORDED</p>
              <p className="text-[9px] text-slate-500 mt-1 max-w-[200px] leading-relaxed mx-auto font-sans">
                Portfolios are synced with Agnes-AI model iterations automatically.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5 pb-8">
            {filteredJobs.map((job) => {
              const pending = job.status === 'pending' || job.status === 'processing';
              
              return (
                <div
                  key={job.id}
                  onClick={() => !pending && setSelectedJob(job)}
                  className="relative rounded-xl overflow-hidden border cursor-pointer select-none aspect-[3/4] flex flex-col group transition-all duration-300 border-white/5 bg-[#161920] hover:border-blue-500/20"
                >
                  {/* Media Content */}
                  {pending ? (
                    // PROGRESS ACTIVE STATE DISPLAY
                    <div className="flex-1 flex flex-col items-center justify-center p-3 relative bg-slate-950/90 text-center select-none overflow-hidden">
                      {/* Grid animated matrix BG */}
                      <div className="absolute inset-0 bg-[radial-gradient(#3b82f6_1.5px,transparent_1.5px)] [background-size:12px_12px] opacity-15 animate-pulse" />
                      
                      <div className="w-8 h-8 rounded-full border-t-[1.5px] border-blue-500 animate-spin flex items-center justify-center mb-2">
                        <Clock className="w-3.5 h-3.5 text-blue-400" />
                      </div>
                      
                      <div className="z-10 mt-1">
                        <span className="text-[9px] font-black text-slate-200 tracking-wider font-mono">
                          {job.progress}% COMPILE
                        </span>
                        <div className="w-16 bg-[#161920] h-1 rounded-full overflow-hidden mt-1 mx-auto leading-none border border-white/5">
                          <div 
                            className="bg-blue-500 h-full rounded-full transition-all duration-300"
                            style={{ width: `${job.progress}%` }}
                          />
                        </div>
                        <p className="text-[7px] text-blue-400 tracking-wider font-bold font-mono uppercase mt-1">
                          {job.type === 'image' ? 'RENDERING STILL' : 'CALCULATING VECTORS'}
                        </p>
                      </div>
                    </div>
                  ) : (
                    // COMPLETED STATE DISPLAY
                    <div className="flex-1 relative overflow-hidden bg-black">
                      <img
                        src={job.resultUrl}
                        alt="result"
                        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                      
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#0F1115] via-[#0F1115]/30 to-transparent p-2">
                        <p className="text-[9.5px] font-bold text-slate-100 truncate">{job.prompt}</p>
                        <p className="text-[7.5px] text-slate-500 mt-0.5 font-mono">
                          ID: #{job.id.substring(4, 10).toUpperCase()} • {job.aspectRatio}
                        </p>
                      </div>
 
                      {/* Header overlay badge */}
                      <div className="absolute top-1.5 left-1.5 flex gap-1">
                        <span className="px-1.5 py-0.2 bg-black/60 rounded border border-white/5 text-[7px] font-mono uppercase text-blue-400 font-bold">
                          {job.type.toUpperCase()}
                        </span>
                      </div>
 
                      {/* Immediate Trash can button */}
                      <button
                        onClick={(e) => handleDeleteJob(job.id, e)}
                        className="absolute top-1.5 right-1.5 p-1 bg-black/50 hover:bg-rose-500 text-slate-400 hover:text-white rounded transition-all"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* PORTFOLIO ITEM FULL SCREEN PREVIEW DRAWEL (High Density Styled matching frame layout) */}
      {selectedJob && (
        <div className="absolute inset-0 bg-[#050505]/85 backdrop-blur-sm z-50 flex items-end justify-center">
          <div 
            className="w-full max-h-[88%] rounded-t-2xl p-4 flex flex-col shadow-2xl transition-all overflow-y-auto bg-[#0F1115] text-slate-100 border-t border-white/10"
          >
            {/* Header / Creator info bar */}
            <div className="flex items-center justify-between border-b pb-3 border-white/5">
              <div className="flex items-center space-x-2">
                <div className="w-6 h-6 rounded bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                  <Sparkles className="w-3.5 h-3.5 text-blue-400 animate-pulse" />
                </div>
                <div>
                  <h4 className="text-[10px] font-bold">PRO ACCOUNT SEED UNIT</h4>
                  <p className="text-[8px] text-slate-500 font-mono">{selectedJob.createdAt}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedJob(null)}
                className="w-5 h-5 rounded bg-[#161920] border border-white/5 flex items-center justify-center text-[10px] font-bold text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            {/* Display Media block inside detail view */}
            <div className="relative mt-2.5 rounded-xl overflow-hidden bg-black flex justify-center aspect-[16/10] sm:aspect-[16/9] items-center mb-2.5 group border border-white/5">
              <img
                src={selectedJob.resultUrl}
                alt="Personal render result"
                className="w-full h-full object-cover"
              />
              {selectedJob.type === 'video' && (
                <div className="absolute inset-0 bg-black/25 flex items-center justify-center">
                  <div className="w-8 h-8 rounded-full bg-blue-500 text-slate-950 flex items-center justify-center shadow-lg transition-transform hover:scale-105">
                    <Play className="w-4 h-4 fill-current ml-0.5" />
                  </div>
                </div>
              )}
            </div>

            {/* Technical meta info listing */}
            <div className="grid grid-cols-3 gap-2 text-[7.5px] text-slate-500 font-bold uppercase tracking-widest font-mono text-center mb-2.5">
              <div className="bg-[#161920] p-1.5 rounded-lg border border-white/5">
                <span className="block text-slate-600 mb-0.5">Ratio</span>
                <span className="text-slate-350">{selectedJob.aspectRatio}</span>
              </div>
              <div className="bg-[#161920] p-1.5 rounded-lg border border-white/5">
                <span className="block text-slate-600 mb-0.5">Asset-Type</span>
                <span className="text-slate-350 font-sans">{selectedJob.type.toUpperCase()}</span>
              </div>
              <div className="bg-[#161920] p-1.5 rounded-lg border border-white/5">
                <span className="block text-slate-600 mb-0.5">Seed-Gate</span>
                <span className="text-slate-350">#492104</span>
              </div>
            </div>

            {/* Prompt details container inside preview */}
            <div className="bg-[#161920] p-2.5 rounded-xl border border-white/5 mb-3.5 text-left">
              <div className="flex justify-between items-start mb-1.5">
                <span className="text-[8px] font-bold uppercase text-slate-500 tracking-wider font-mono">SYNTHESIZED PROMPT TOKEN</span>
                <button
                  onClick={() => handleCopyPrompt(selectedJob.prompt)}
                  className={`text-[8.5px] font-mono flex items-center gap-1 py-0.5 px-1.5 rounded transition-all ${
                    copied 
                    ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' 
                    : 'bg-[#0F1115] border border-white/5 text-slate-400 hover:text-slate-205 font-bold'
                  }`}
                >
                  {copied ? 'COPIED!' : 'COPY'}
                </button>
              </div>
              <p className="text-[9.5px] text-slate-350 leading-relaxed font-mono select-text bg-[#0F1115] p-2 rounded-lg border border-white/5 max-h-24 overflow-y-auto">
                {selectedJob.prompt}
              </p>
            </div>

            {/* Downloader trigger action bar */}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  triggerExportNotification();
                }}
                className="flex-1 py-2 bg-blue-500 text-slate-950 font-bold text-[11px] rounded-xl flex items-center justify-center gap-1.5 transition-all hover:scale-[1.01] active:scale-[0.99] uppercase shadow-[0_0_15px_rgba(59,130,246,0.3)]"
              >
                <Download className="w-3.5 h-3.5 text-slate-950" />
                Raw HQ Download
              </button>
              
              <button
                type="button"
                onClick={(e) => {
                  handleDeleteJob(selectedJob.id, e);
                  setSelectedJob(null);
                }}
                className="p-2 bg-rose-500/10 hover:bg-rose-500 text-rose-450 hover:text-white rounded-xl border border-rose-500/20 transition-all active:scale-[0.99] flex items-center justify-center"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
