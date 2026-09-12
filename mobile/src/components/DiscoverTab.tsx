import React, { useState } from 'react';
import { Search, Heart, Eye, Play, Sparkles, Copy, Check, ArrowRight, Share2, Compass, Film, ImageIcon } from 'lucide-react';
import { GalleryItem, GenType } from '../types';

interface DiscoverTabProps {
  items: GalleryItem[];
  setItems: React.Dispatch<React.SetStateAction<GalleryItem[]>>;
  onUsePrompt: (prompt: string, type: GenType, modelName: string, aspectRatio: string) => void;
  theme: 'dark' | 'light';
}

export default function DiscoverTab({ items, setItems, onUsePrompt, theme }: DiscoverTabProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'image' | 'video'>('all');
  const [selectedItem, setSelectedItem] = useState<GalleryItem | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Filter items
  const filteredItems = items.filter((item) => {
    const matchesSearch = item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          item.prompt.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = activeFilter === 'all' || item.type === activeFilter;
    return matchesSearch && matchesCategory;
  });

  const handleLike = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setItems((prev) =>
      prev.map((item) => {
        if (item.id === id) {
          const isLiked = !item.isLiked;
          return {
            ...item,
            isLiked,
            likes: isLiked ? item.likes + 1 : item.likes - 1,
          };
        }
        return item;
      })
    );
    // If the modal is currently open and has this item selected, synchronize it
    if (selectedItem && selectedItem.id === id) {
      setSelectedItem((prev) => {
        if (!prev) return null;
        const isLiked = !prev.isLiked;
        return {
          ...prev,
          isLiked,
          likes: isLiked ? prev.likes + 1 : prev.likes - 1,
        };
      });
    }
  };

  const handleCopyPrompt = (prompt: string, id: string) => {
    navigator.clipboard.writeText(prompt);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div id="discover-tab" className="h-full flex flex-col pt-2 overflow-hidden select-none">
      
      {/* Header with Title & User Details (High Density Theme alignment) */}
      <div className="px-4 pb-2 flex items-center justify-between mt-1">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)] flex shrink-0"></span>
            Agnes<span className="text-blue-500">AI</span>
            <span className="text-[10px] text-slate-500 font-mono font-normal ml-0.5">/ DISCOVER</span>
          </h2>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">Curated Engine Masterworks</p>
        </div>
        
        {/* Dynamic active user count badge (Prism look) */}
        <div className="flex items-center gap-1 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded-md">
          <span className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[8px] font-bold text-blue-400 font-mono">1,894 ONLINE</span>
        </div>
      </div>

      {/* Search Input Box */}
      <div className="px-4 mb-2.5">
        <div className="relative">
          <input
            type="text"
            placeholder="Filter prompts, seed tokens, styles..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full text-[11px] py-1.5 px-3 pl-8 rounded-xl border border-white/5 outline-none transition-all duration-300 bg-[#161920] text-slate-100 placeholder-slate-500 focus:border-blue-500/30 font-mono"
          />
          <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-slate-500" />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-2 text-slate-400 hover:text-slate-200 text-[9px] font-bold font-mono"
            >
              CLEAR
            </button>
          )}
        </div>
      </div>

      {/* Category Pills Filters (Sleek Compact Buttons) */}
      <div className="px-4 mb-2.5 flex items-center space-x-1.5 overflow-x-auto scrollbar-none shrink-0">
        <button
          onClick={() => setActiveFilter('all')}
          className={`px-2.5 py-1 text-[10px] font-semibold rounded-lg transition-all duration-200 ${
            activeFilter === 'all'
              ? 'bg-blue-500 text-slate-950 font-bold shadow-[0_0_10px_rgba(59,130,246,0.3)]'
              : 'bg-[#161920] text-slate-400 hover:text-slate-200 border border-white/5'
          }`}
        >
          Σ ALL PIPES
        </button>
        <button
          onClick={() => setActiveFilter('image')}
          className={`px-2.5 py-1 text-[10px] font-semibold rounded-lg flex items-center gap-1 transition-all duration-200 ${
            activeFilter === 'image'
              ? 'bg-blue-500 text-slate-950 font-bold shadow-[0_0_10px_rgba(59,130,246,0.3)]'
              : 'bg-[#161920] text-slate-400 hover:text-slate-200 border border-white/5'
          }`}
        >
          <ImageIcon className="w-2.5 h-2.5" />
          IMAGES
        </button>
        <button
          onClick={() => setActiveFilter('video')}
          className={`px-2.5 py-1 text-[10px] font-semibold rounded-lg flex items-center gap-1 transition-all duration-200 ${
            activeFilter === 'video'
              ? 'bg-blue-500 text-slate-950 font-bold shadow-[0_0_10px_rgba(59,130,246,0.3)]'
              : 'bg-[#161920] text-slate-400 hover:text-slate-200 border border-white/5'
          }`}
        >
          <Film className="w-2.5 h-2.5" />
          VIDEOS
        </button>
      </div>

      {/* Grid of creations */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 scrollbar-none">
        {filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center space-y-3">
            <div className="w-12 h-12 rounded-xl bg-[#161920] border border-white/5 flex items-center justify-center">
              <Search className="w-4 h-4 text-slate-500 animate-pulse" />
            </div>
            <p className="text-[10px] font-mono text-slate-500">No telemetry matches query parameters.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2.5">
            {filteredItems.map((item) => (
              <div
                key={item.id}
                onClick={() => setSelectedItem(item)}
                className="group relative rounded-xl overflow-hidden shadow-2xl cursor-pointer border border-white/5 bg-[#161920] hover:border-blue-500/25 transition-all duration-300"
              >
                {/* Media frame */}
                <div className="relative aspect-[3/4] overflow-hidden bg-slate-950">
                  <img
                    src={item.imageUrl}
                    alt={item.title}
                    referrerPolicy="no-referrer"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  
                  {/* Subtle black overlay shadow */}
                  <div className="absolute inset-0 bg-gradient-to-t from-[#0F1115] via-[#0F1115]/20 to-transparent" />

                  {/* Badges */}
                  {item.type === 'video' ? (
                    <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-blue-500 text-slate-950 rounded text-[7px] font-black tracking-widest flex items-center gap-0.5 shadow">
                      <Play className="w-2 h-2 fill-current" />
                      <span>LIVE</span>
                    </div>
                  ) : (
                    <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-slate-800/80 border border-white/5 text-slate-205 rounded text-[7px] font-mono tracking-wide flex items-center shadow">
                      <span>STILL</span>
                    </div>
                  )}

                  {/* Prompt Text snippet inside overlay */}
                  <div className="absolute bottom-1.5 left-1.5 right-1.5 flex flex-col">
                    <p className="text-[9.5px] font-bold text-white truncate">{item.title}</p>
                    <p className="text-[8px] text-slate-400 font-mono truncate">
                      @{item.author.name.toLowerCase()}
                    </p>
                  </div>

                  {/* Likes pill on the top right */}
                  <button
                    onClick={(e) => handleLike(item.id, e)}
                    className={`absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold flex items-center justify-center space-x-0.5 backdrop-blur-md border transition-all active:scale-90 ${
                      item.isLiked
                        ? 'bg-rose-500 text-white border-rose-400/20'
                        : 'bg-black/40 text-slate-200 border-white/5 hover:bg-black/60'
                    }`}
                  >
                    <Heart className={`w-2 h-2 ${item.isLiked ? 'fill-current text-white' : 'text-slate-300'}`} />
                    <span className="font-mono text-[7px] leading-none">{item.likes}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* DETAIL DRAWER / POPAL DIALOG (High Density styling matching the dark frame container) */}
      {selectedItem && (
        <div className="absolute inset-0 bg-[#050505]/85 backdrop-blur-sm z-50 flex items-end justify-center">
          <div 
            className="w-full max-h-[88%] rounded-t-2xl p-4 flex flex-col shadow-2xl transition-all overflow-y-auto bg-[#0F1115] text-slate-200 border-t border-white/10"
          >
            {/* Header / Grabber */}
            <div className="flex items-center justify-between border-b pb-3 border-white/5">
              <div className="flex items-center space-x-2">
                <img
                  src={selectedItem.author.avatar}
                  alt={selectedItem.author.name}
                  className="w-6 h-6 rounded-lg object-cover border border-[#1C1F26]"
                />
                <div>
                  <div className="flex items-center space-x-1">
                    <span className="text-[10px] font-bold">@{selectedItem.author.name}</span>
                    <span className="px-1 py-0.2 bg-blue-500/10 border border-blue-500/20 text-blue-400 rounded text-[7px] font-bold font-mono">
                      {selectedItem.author.tier.toUpperCase()} CREATOR
                    </span>
                  </div>
                  <p className="text-[8px] text-slate-500 font-mono tracking-tight">{selectedItem.modelName}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedItem(null)}
                className="w-5 h-5 rounded-lg flex items-center justify-center text-[10px] font-bold bg-[#161920] text-slate-400 hover:text-slate-200 border border-white/5"
              >
                ✕
              </button>
            </div>

            {/* Display Media */}
            <div className="relative mt-2.5 rounded-xl overflow-hidden bg-black flex justify-center aspect-[16/10] sm:aspect-[16/9] items-center mb-2.5 group border border-white/5">
              <img
                src={selectedItem.imageUrl}
                alt={selectedItem.title}
                className="w-full h-full object-cover"
                referrerPolicy="no-referrer"
              />
              {selectedItem.type === 'video' && (
                <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
                  <div className="w-8 h-8 rounded-full bg-blue-500 text-[#0F1115] flex items-center justify-center shadow-lg transition-transform">
                    <Play className="w-4 h-4 fill-current ml-0.5" />
                  </div>
                </div>
              )}
            </div>

            {/* Meta counters info row */}
            <div className="flex items-center space-x-4 text-[9px] text-slate-500 mb-2.5 px-1 font-mono">
              <span className="flex items-center gap-1">
                <Eye className="w-3.5 h-3.5 text-slate-600" />
                {selectedItem.views} VIEWS
              </span>
              <button 
                onClick={(e) => handleLike(selectedItem.id, e)}
                className={`flex items-center gap-1 transition-all ${selectedItem.isLiked ? 'text-rose-400 font-bold' : ''}`}
              >
                <Heart className={`w-3.5 h-3.5 ${selectedItem.isLiked ? 'fill-current text-rose-400' : 'text-slate-600'}`} />
                {selectedItem.likes} LIKES
              </button>
              <span className="bg-[#161920] border border-white/5 px-1.5 py-0.5 rounded text-[7.5px] font-semibold text-slate-300">
                RATIO {selectedItem.aspectRatio}
              </span>
            </div>

            {/* Prompt details scroll box (Technical terminal look) */}
            <div className="flex-1 bg-[#161920] p-2.5 rounded-xl border border-white/5 mb-3.5 text-left">
              <div className="flex justify-between items-start mb-1.5">
                <span className="text-[8px] font-black uppercase text-slate-500 tracking-wider font-mono">PROMPT SEQUENCE TOKENS</span>
                <button
                  onClick={() => handleCopyPrompt(selectedItem.prompt, selectedItem.id)}
                  className={`text-[8.5px] font-mono flex items-center gap-1 py-0.5 px-1.5 rounded transition-all ${
                    copiedId === selectedItem.id 
                    ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' 
                    : 'bg-[#0F1115] border border-white/5 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {copiedId === selectedItem.id ? 'COPIED!' : 'COPY'}
                </button>
              </div>
              <p className="text-[10px] text-slate-300 leading-relaxed font-mono select-text bg-[#0F1115] p-2 rounded-lg border border-white/5 max-h-24 overflow-y-auto">
                {selectedItem.prompt}
              </p>
            </div>

            {/* Actions button */}
            <button
              onClick={() => {
                onUsePrompt(
                  selectedItem.prompt,
                  selectedItem.type,
                  selectedItem.modelName,
                  selectedItem.aspectRatio
                );
                setSelectedItem(null); // auto close
              }}
              className="w-full py-2 bg-blue-500 text-slate-950 font-bold text-[11px] rounded-xl flex items-center justify-center gap-1.5 transition-all hover:scale-[1.01] active:scale-[0.99] tracking-wider uppercase shadow-[0_0_15px_rgba(59,130,246,0.3)]"
            >
              <Sparkles className="w-3.5 h-3.5 text-[#0F1115]" />
              LOAD PARAMETERS INTO ENGINE
              <ArrowRight className="w-3 h-3 text-[#0F1115]" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
