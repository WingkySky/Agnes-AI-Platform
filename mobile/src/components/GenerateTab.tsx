import React, { useState } from 'react';
import { Sparkles, Sliders, Play, Smartphone, Square, Tv, Monitor, RectangleVertical, HelpCircle, Loader2, ArrowRight } from 'lucide-react';
import { GenType, AIModel, AspectRatio, StylePreset } from '../types';
import { AI_MODELS, ASPECT_RATIOS, STYLE_PRESETS } from '../data';

interface GenerateTabProps {
  initialPrompt: string;
  setInitialPrompt: React.Dispatch<React.SetStateAction<string>>;
  initialType: GenType;
  setInitialType: React.Dispatch<React.SetStateAction<GenType>>;
  initialModel: string;
  setInitialModel: React.Dispatch<React.SetStateAction<string>>;
  initialAspectRatio: string;
  setInitialAspectRatio: React.Dispatch<React.SetStateAction<string>>;
  onSynthesize: (
    prompt: string,
    type: GenType,
    modelId: string,
    aspectRatio: string,
    videoConfig?: { duration: number; motionStrength: number; cameraMovement: string }
  ) => void;
  userCredits: number;
  theme: 'dark' | 'light';
}

export default function GenerateTab({
  initialPrompt,
  setInitialPrompt,
  initialType,
  setInitialType,
  initialModel,
  setInitialModel,
  initialAspectRatio,
  setInitialAspectRatio,
  onSynthesize,
  userCredits,
  theme
}: GenerateTabProps) {
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isExpanding, setIsExpanding] = useState(false);
  
  // Advanced parameters
  const [negativePrompt, setNegativePrompt] = useState('low quality, blurry, deformed fingers, extra limbs, web addresses, text');
  const [guidanceScale, setGuidanceScale] = useState(7.5);
  const [steps, setSteps] = useState(30);

  // Video-specific settings
  const [duration, setDuration] = useState(4); // 4 or 8 seconds
  const [motionStrength, setMotionStrength] = useState(5); // 1-10
  const [cameraMovement, setCameraMovement] = useState('Steady Zoom-In');

  // Filter models matched list
  const filteredModels = AI_MODELS.filter(
    (model) => model.type === initialType || model.type === 'both'
  );

  // Quick prompt presets for clicking references
  const handleSelectPreset = (preset: StylePreset) => {
    setSelectedPreset(preset.id);
    // Append or add style
    if (!initialPrompt.includes(preset.promptSuffix)) {
      setInitialPrompt((prev) => {
        // Clean trailing spaces or commas
        const trimmed = prev.trim();
        if (!trimmed) {
          return `A gorgeous scene${preset.promptSuffix}`;
        }
        return `${trimmed}${preset.promptSuffix}`;
      });
    }
  };

  // Magic Enhancer: Expands simple prompt to ultra artistic prompt
  const handleMagicEnhance = () => {
    if (!initialPrompt.trim()) {
      setInitialPrompt("Cinematic close-up of a legendary golden phoenix rising from neon cosmic energy, high-fidelity digital art, unreal engine 5, octane render");
      return;
    }
    
    setIsExpanding(true);
    setTimeout(() => {
      setIsExpanding(false);
      const subjects = [
        "shot on Hasselblad 85mm portrait lens, breathtaking cinematic lighting, volumetric atmosphere, hyperrealistic detailing, rich tactile textures, warm color grading",
        "extremely detailed digital painting, vibrant surreal ambiance, sharp focus, trend on artstation, masterpiece, mystical atmosphere, golden dust elements, dramatic shadows",
        "anime style key visual, beautiful Kyoto-studio-inspired lighting, gorgeous sunset horizon, vibrant hues, hyper realistic clouds, dreamy 8k resolution, crisp line-art"
      ];
      const selected = subjects[Math.floor(Math.random() * subjects.length)];
      setInitialPrompt((prev) => `${prev.trim()}, ${selected}`);
    }, 1200);
  };

  // Run the generation trigger
  const handleGenerateClick = () => {
    if (!initialPrompt.trim()) return;

    const videoConfig = initialType === 'video' ? {
      duration,
      motionStrength,
      cameraMovement
    } : undefined;

    onSynthesize(
      initialPrompt,
      initialType,
      initialModel,
      initialAspectRatio,
      videoConfig
    );
  };

  // Helper icons selector mapping
  const renderAspectIcon = (iconName: string) => {
    switch (iconName) {
      case 'Square': return <Square className="w-4 h-4" />;
      case 'Smartphone': return <Smartphone className="w-4 h-4" />;
      case 'RectangleVertical': return <RectangleVertical className="w-4 h-4" />;
      case 'Tv': return <Tv className="w-4 h-4" />;
      case 'Monitor': return <Monitor className="w-4 h-4" />;
      default: return <Square className="w-4 h-4" />;
    }
  };

  return (
    <div id="generate-tab" className="h-full flex flex-col pt-2 overflow-hidden text-left select-none">
      
      {/* Top Toggle Switch for Image vs Video (High Density Style) */}
      <div className="px-4 pb-2 flex items-center justify-between shrink-0 mt-1">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)] flex shrink-0"></span>
            Agnes<span className="text-blue-500">AI</span>
            <span className="text-[10px] text-slate-500 font-mono font-normal ml-0.5">/ ENGINE</span>
          </h2>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">Synthesis Parameter console</p>
        </div>

        {/* Core Type Switch */}
        <div className="flex bg-[#161920] border border-white/5 p-0.5 rounded-xl">
          <button
            onClick={() => {
              setInitialType('image');
              setInitialModel('agnes-vision-ultra');
            }}
            className={`px-3 py-1 text-[9px] font-bold rounded-lg transition-all ${
              initialType === 'image'
                ? 'bg-blue-500 text-slate-950 font-extrabold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            STILL
          </button>
          <button
            onClick={() => {
              setInitialType('video');
              setInitialModel('agnes-motion-cinematic');
            }}
            className={`px-3 py-1 text-[9px] font-bold rounded-lg transition-all ${
              initialType === 'video'
                ? 'bg-blue-500 text-slate-950 font-extrabold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            MOTION
          </button>
        </div>
      </div>

      {/* Main Form Fields scroll box */}
      <div className="flex-1 overflow-y-auto px-4 pb-3 space-y-3.5 scrollbar-none">
        
        {/* Core Prompt Box */}
        <div className="space-y-1.5">
          <div className="flex justify-between items-center px-0.5">
            <span className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest font-mono">
              PROMPT DESCRIPTOR SEED
            </span>
            <button
              onClick={handleMagicEnhance}
              disabled={isExpanding}
              className="text-[9px] font-black text-blue-450 hover:text-blue-400 flex items-center gap-1 active:scale-95 transition-all"
            >
              {isExpanding ? (
                <>
                  <Loader2 className="w-2.5 h-2.5 animate-spin text-blue-500" />
                  EXPANDING...
                </>
              ) : (
                <>
                  <Sparkles className="w-2.5 h-2.5 text-blue-400 animate-pulse" />
                  MAGIC EXPAND (智能拓展)
                </>
              )}
            </button>
          </div>
          
          <div className="relative">
            <textarea
              value={initialPrompt}
              onChange={(e) => setInitialPrompt(e.target.value)}
              placeholder={
                initialType === 'image'
                  ? "Describe what you want to synthesize... e.g. 'A cozy tea house inside a giant hollow ancient tree with glowing amber fireflies...'"
                  : "Describe cinematic movement... e.g. 'A slow crane down on a cybernetic dragon curled around an electric pillar, breathing neon smoke...'"
              }
              className="w-full h-22 text-[11px] p-2.5 rounded-xl bg-[#161920] border border-white/5 text-slate-200 outline-none focus:border-blue-500/20 placeholder-slate-500 resize-none font-sans leading-relaxed"
            />
            {initialPrompt.trim().length > 0 && (
              <button
                onClick={() => setInitialPrompt('')}
                className="absolute bottom-2.5 right-2 px-1.5 py-0.5 bg-[#0F1115] text-[8px] font-bold rounded text-slate-400 hover:text-slate-200 hover:bg-[#161920]"
              >
                CLEAR
              </button>
            )}
          </div>
        </div>

        {/* Style Presets lists */}
        <div className="space-y-1.5 select-none">
          <span className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block px-0.5 font-mono">
            ARTISTIC PRESETS SUFFIX
          </span>
          <div className="flex space-x-2 overflow-x-auto pb-1 scrollbar-none">
            {STYLE_PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => handleSelectPreset(preset)}
                className={`flex-shrink-0 flex flex-col items-center space-y-1 group relative rounded-lg overflow-hidden focus:outline-none transition-all ${
                  selectedPreset === preset.id ? 'scale-95 ring-[1.5px] ring-blue-500' : 'hover:opacity-90'
                }`}
              >
                <div className="w-11 h-11 rounded-lg overflow-hidden relative border border-white/5">
                  <img src={preset.image} alt={preset.name} className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/40 group-hover:bg-black/20 transition-all" />
                  <div className="absolute bottom-0.5 left-0 right-0 text-center text-[7px] font-black text-slate-200 uppercase tracking-tighter truncate px-0.5">
                    {preset.name.split(' ')[0]}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Core Generator engine selection */}
        <div className="space-y-1.5">
          <span className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block px-0.5 font-mono">
            ACTIVE SYNTH ENGINE MODEL
          </span>
          <div className="space-y-1.5">
            {filteredModels.map((model) => (
              <div
                key={model.id}
                onClick={() => setInitialModel(model.id)}
                className={`p-2.5 rounded-xl border text-left cursor-pointer transition-all ${
                  initialModel === model.id
                    ? 'bg-blue-500/5 border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.15)]'
                    : 'bg-[#161920] border-white/5 hover:bg-slate-800'
                }`}
              >
                <div className="flex justify-between items-center mb-0.5">
                  <h4 className="text-[11px] font-bold text-slate-100 flex items-center gap-1.5">
                    {model.name}
                    {model.badge && (
                      <span className="px-1 py-0.2 bg-blue-550/10 border border-blue-500/20 text-blue-400 rounded-sm text-[7px] font-bold tracking-wide">
                        {model.badge}
                      </span>
                    )}
                  </h4>
                  <span className="text-[8px] text-slate-500 font-mono">{model.speed}</span>
                </div>
                <p className="text-[9.5px] text-slate-400 font-sans leading-tight">
                  {model.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Aspect Ratio block */}
        <div className="space-y-1.5">
          <span className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block px-0.5 font-mono">
            BOUNDING ASPECT RATIO
          </span>
          <div className="grid grid-cols-5 gap-1.5 select-none">
            {ASPECT_RATIOS.map((ratio) => (
              <button
                key={ratio.id}
                onClick={() => setInitialAspectRatio(ratio.value)}
                className={`py-1.5 rounded-lg border flex flex-col items-center justify-center space-y-0.5 transition-all ${
                  initialAspectRatio === ratio.value
                    ? 'bg-blue-500 border-blue-500 text-slate-950 font-bold shadow-[0_0_10px_rgba(59,130,246,0.3)]'
                    : 'bg-[#161920] border-white/5 text-slate-400 hover:text-slate-100'
                }`}
              >
                {renderAspectIcon(ratio.icon)}
                <span className="text-[8px] font-bold font-mono">{ratio.value}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Video specific configuration options container */}
        {initialType === 'video' && (
          <div className="p-3 bg-[#161920] border border-white/5 rounded-xl space-y-3">
            <h3 className="text-[8.5px] font-bold text-slate-300 uppercase tracking-widest flex items-center gap-1.5 font-mono">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full" />
              DIRECTOR MOTION GRAPH PARAMETERS
            </h3>

            {/* Video Duration */}
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[8px] text-slate-500 font-mono">
                <span>SCENE DURATION LIMIT</span>
                <span className="font-bold text-blue-400">{duration} SECONDS</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setDuration(4)}
                  className={`py-1 rounded-lg border font-bold text-[10px] transition-all ${
                    duration === 4
                      ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                      : 'bg-[#0F1115] border-white/5 text-slate-400'
                  }`}
                >
                  Standard Clip (4s)
                </button>
                <button
                  type="button"
                  onClick={() => setDuration(8)}
                  className={`py-1 rounded-lg border font-bold text-[10px] transition-all ${
                    duration === 8
                      ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                      : 'bg-[#0F1115] border-white/5 text-slate-400'
                  }`}
                >
                  Extended Clip (8s)
                </button>
              </div>
            </div>

            {/* Motion strength slider */}
            <div className="space-y-1">
              <div className="flex justify-between items-center text-[8px] text-slate-500 font-mono">
                <span>MOTION INTENSITY GRAPH</span>
                <span className="font-bold text-blue-400">LEVEL {motionStrength} / 10</span>
              </div>
              <input
                type="range"
                min="1"
                max="10"
                value={motionStrength}
                onChange={(e) => setMotionStrength(parseInt(e.target.value))}
                className="w-full accent-blue-500 bg-[#0F1115] h-1 rounded"
              />
            </div>

            {/* Camera movement presets */}
            <div className="space-y-1">
              <span className="text-[8px] text-slate-500 uppercase tracking-widest block font-mono">CAMERA VECTOR ANCHOR</span>
              <div className="grid grid-cols-3 gap-1 text-[8.5px] font-bold select-none">
                {['Steady Zoom-In', 'Fast Orbit Left', 'Tilt-Up Pan', 'Cinematic Drone', 'Handheld Jitter', 'Slow Motion Roll'].map(
                  (mov) => (
                    <button
                      key={mov}
                      type="button"
                      onClick={() => setCameraMovement(mov)}
                      className={`py-1 rounded border truncate px-1 transition-all ${
                        cameraMovement === mov
                          ? 'bg-blue-500/20 border-blue-500 text-blue-400'
                          : 'bg-[#0F1115] border-white/5 text-slate-500 hover:text-slate-350'
                      }`}
                    >
                      {mov}
                    </button>
                  )
                )}
              </div>
            </div>
          </div>
        )}

        {/* Toggle Advanced Parameter Expand */}
        <div>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-[9px] font-medium text-slate-500 hover:text-slate-300 flex items-center gap-1.5 py-0.5 mt-0.5 outline-none font-mono"
          >
            <Sliders className="w-3 h-3 text-slate-600" />
            {showAdvanced ? 'HIDE TELEMETRY TUNER (✕)' : 'DEVELOPER TUNING CHANNELS (▼)'}
          </button>

          {showAdvanced && (
            <div className="mt-2 p-2.5 bg-[#161920] rounded-xl border border-white/5 space-y-2.5">
              {/* Negative prompt */}
              <div className="space-y-1 text-left">
                <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest block font-mono">
                  NEGATIVE WEIGHT EXCLUSIONS
                </span>
                <input
                  type="text"
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  className="w-full text-[10px] py-1 px-2.5 rounded-lg bg-[#0F1115] border border-white/5 text-slate-300 outline-none focus:border-blue-500/30 font-mono"
                />
              </div>

              {/* Guidance scale and Steps */}
              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1 text-left">
                  <div className="flex justify-between items-center text-[8px] text-slate-500 font-mono">
                    <span>CFG RATIO</span>
                    <span className="font-bold text-blue-400">{guidanceScale}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="20"
                    step="0.5"
                    value={guidanceScale}
                    onChange={(e) => setGuidanceScale(parseFloat(e.target.value))}
                    className="w-full accent-blue-500 bg-[#0F1115] h-1 rounded shadow"
                  />
                </div>

                <div className="space-y-1 text-left">
                  <div className="flex justify-between items-center text-[8px] text-slate-500 font-mono">
                    <span>STEPS</span>
                    <span className="font-bold text-blue-400">{steps}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1 text-[8px] font-bold font-mono">
                    {[15, 30, 50].map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setSteps(s)}
                        className={`py-0.5 rounded border ${
                          steps === s
                            ? 'bg-blue-500/10 border-blue-500 text-blue-400'
                            : 'bg-[#0F1115] border-white/5 text-slate-500'
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* FOOTER: Fixed Synthesize Action bar with credits count */}
      <div className="p-3 bg-[#0F1115] border-t border-white/5 shrink-0 select-none">
        <button
          onClick={handleGenerateClick}
          disabled={!initialPrompt.trim()}
          className={`w-full py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-md ${
            initialPrompt.trim()
              ? 'bg-blue-500 text-[#0F1115] hover:scale-[1.01] active:scale-[0.99] shadow-[0_0_15px_rgba(59,130,246,0.3)] cursor-pointer'
              : 'bg-[#161920] border border-white/5 text-slate-650 cursor-not-allowed'
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>SYNTHESIZE WORK</span>
          <span className="text-[8px] px-1.5 py-0.2 bg-black/15 text-[#0F1115] font-extrabold rounded-md border border-neutral-900/10">
            {initialType === 'image' ? 'COST 2' : 'COST 5'} CR
          </span>
          <ArrowRight className="w-3 h-3" />
        </button>

        <p className="text-[8.5px] text-slate-500 text-center mt-2 font-mono">
          UNITS AVAILABLE: <span className="font-bold text-blue-400">{userCredits} CREDITS</span> • GPU CONSOLE SPEED: <span className="text-emerald-400 font-bold">FAST (~3s)</span>
        </p>
      </div>
    </div>
  );
}
