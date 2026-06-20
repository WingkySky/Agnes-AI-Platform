import React, { useState, useEffect } from 'react';
import { Compass, Sparkles, MessageSquare, FolderHeart, User, Bell, AlertCircle } from 'lucide-react';
import PhoneContainer from './components/PhoneContainer';
import DiscoverTab from './components/DiscoverTab';
import GenerateTab from './components/GenerateTab';
import AssistantTab from './components/AssistantTab';
import CreationsTab from './components/CreationsTab';
import ProfileTab from './components/ProfileTab';

import { AppTab, GenType, GenerationJob, GalleryItem, ChatMessage } from './types';
import { INITIAL_GALLERY_ITEMS, INITIAL_CHAT_MESSAGES } from './data';

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>('discover');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [userCredits, setUserCredits] = useState(240);
  const [galleryItems, setGalleryItems] = useState<GalleryItem[]>(INITIAL_GALLERY_ITEMS);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  
  // Create preloaded past creation jobs so user has a rich experience immediately.
  // We seed this with our pre-generated beautiful assets!
  const [jobs, setJobs] = useState<GenerationJob[]>([
    {
      id: 'job-cyber-maiden',
      prompt: 'A close up cinematic portrait of a cyberpunk female pilot with soft neon facial markings, reflective visor, intricate cybernetic headwear, wearing a vintage bomber jacket, glowing blue and pink ambient light, high-end photography, cinematic, 8k resolution, detailed texture',
      type: 'image',
      modelId: 'agnes-vision-ultra',
      aspectRatio: '3:4',
      status: 'completed',
      progress: 100,
      resultUrl: '/src/assets/images/cyber_girl_portrait_1781971382057.jpg',
      createdAt: 'Today, 8:42 AM'
    },
    {
      id: 'job-floating-temple',
      prompt: 'A breathtaking fantasy landscape of an ancient floating stone temple carved into a massive levitating crystal rock, cascading waterfalls pouring down into infinite space, golden sunrays filtering through fluffy pink clouds, majestic birds soaring, ethereal and dreamy atmosphere, unreal engine 5 render, highly detailed, masterpieces',
      type: 'image',
      modelId: 'agnes-vision-ultra',
      aspectRatio: '3:4',
      status: 'completed',
      progress: 100,
      resultUrl: '/src/assets/images/floating_temple_fantasy_1781971398624.jpg',
      createdAt: 'Yesterday, 4:15 PM'
    },
    {
      id: 'job-retro-car',
      prompt: 'A sleek retro-futuristic black hover sports car with glowing turquoise booster lights flying over a cyber-synthwave neon-lit highway at night, towering holographic buildings in the background, purple mist, vaporwave aesthetics, motion blur, extremely high resolution, cinematic framing',
      type: 'video',
      modelId: 'agnes-motion-cinematic',
      aspectRatio: '16:9',
      status: 'completed',
      progress: 100,
      resultUrl: '/src/assets/images/retro_cyber_car_1781971412978.jpg',
      createdAt: 'Yesterday, 11:32 AM'
    }
  ]);

  // Form states inside generator console
  const [formPrompt, setFormPrompt] = useState('');
  const [formType, setFormType] = useState<GenType>('image');
  const [formModel, setFormModel] = useState('agnes-vision-ultra');
  const [formAspectRatio, setFormAspectRatio] = useState('3:4');

  // Dynamic system toast notifications
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Live render simulator scheduling loop
  useEffect(() => {
    const hasActiveJobs = jobs.some((j) => j.status === 'pending' || j.status === 'processing');
    if (!hasActiveJobs) return;

    const timer = setInterval(() => {
      setJobs((prevJobs) => {
        let updated = false;
        const next = prevJobs.map((job) => {
          if (job.status === 'pending') {
            updated = true;
            return { ...job, status: 'processing', progress: 12 };
          }
          if (job.status === 'processing') {
            updated = true;
            const step = Math.floor(Math.random() * 20) + 12;
            const nextProgress = job.progress + step;
            if (nextProgress >= 100) {
              // Trigger final rendering asset photo assignment
              let finalizedUrl = 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80'; // fallback
              const promptLower = job.prompt.toLowerCase();
              
              if (promptLower.includes('cyber') || promptLower.includes('girl') || promptLower.includes('mech')) {
                finalizedUrl = '/src/assets/images/cyber_girl_portrait_1781971382057.jpg';
              } else if (promptLower.includes('temple') || promptLower.includes('magic') || promptLower.includes('fantasy') || promptLower.includes('crystal')) {
                finalizedUrl = '/src/assets/images/floating_temple_fantasy_1781971398624.jpg';
              } else if (promptLower.includes('car') || promptLower.includes('highway') || promptLower.includes('road') || promptLower.includes('drift')) {
                finalizedUrl = '/src/assets/images/retro_cyber_car_1781971412978.jpg';
              } else if (job.type === 'video') {
                finalizedUrl = 'https://images.unsplash.com/photo-1541701494587-cb58502866ab?w=600&auto=format&fit=crop&q=80';
              } else {
                // Return a nice dynamic scenic nature picture
                finalizedUrl = 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=600&auto=format&fit=crop&q=80';
              }

              // Show dynamic complete alert inside Dynamic Island Notch!
              setToastMessage(`✨ GPU Synthesized Done: "${job.prompt.substring(0, 18)}..."`);
              setTimeout(() => {
                setToastMessage(null);
              }, 4500);

              return {
                ...job,
                status: 'completed',
                progress: 100,
                resultUrl: finalizedUrl
              };
            }
            return { ...job, progress: nextProgress };
          }
          return job;
        });

        return updated ? next : prevJobs;
      });
    }, 1500);

    return () => clearInterval(timer);
  }, [jobs]);

  // Command Action 1: Re-use prompt from discover list
  const handleUsePrompt = (prompt: string, type: GenType, modelName: string, aspectRatio: string) => {
    setFormPrompt(prompt);
    setFormType(type);
    
    // Attempt matched models mapping
    if (type === 'image') {
      setFormModel('agnes-vision-ultra');
    } else {
      setFormModel('agnes-motion-cinematic');
    }

    setFormAspectRatio(aspectRatio);
    setActiveTab('generate');

    // Mini bottom-slide notice
    setToastMessage("📋 Prompt settings applied to Agnes Engine!");
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Command Action 2: Import prompt directly from Agnes AI Assistant chatbot
  const handleImportPromptFromChatClient = (prompt: string, type: GenType) => {
    setFormPrompt(prompt);
    setFormType(type);
    if (type === 'image') {
      setFormModel('agnes-vision-ultra');
    } else {
      setFormModel('agnes-motion-cinematic');
    }
    setFormAspectRatio('3:4');
    setActiveTab('generate');

    setToastMessage("⚡ AI Optimized prompt exported to Generator!");
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Command Action 3: Trigger the render synthesized click
  const handleSynthesizeLaunch = (
    prompt: string,
    type: GenType,
    modelId: string,
    aspectRatio: string,
    videoConfig?: { duration: number; motionStrength: number; cameraMovement: string }
  ) => {
    const cost = type === 'image' ? 2 : 5;
    if (userCredits < cost) {
      alert("❌ Insufficient Agnes Credits! Please visit the Tiers panel or make a Daily Check-In to secure more computing units.");
      return;
    }

    // Deduct credits in state
    setUserCredits((prev) => prev - cost);

    // Capture standard creation parameters
    const newJob: GenerationJob = {
      id: `job-${Date.now()}`,
      prompt,
      type,
      modelId,
      aspectRatio,
      status: 'pending',
      progress: 0,
      createdAt: 'Today, Just Now',
      ...(type === 'video' && videoConfig ? {
        duration: videoConfig.duration,
        motionStrength: videoConfig.motionStrength,
        cameraMovement: videoConfig.cameraMovement
      } : {})
    };

    // Prepend job and switch tabs
    setJobs((prev) => [newJob, ...prev]);
    setActiveTab('creations');

    setToastMessage("🚀 GPU Queue assigned. Synthesis started!");
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Active creations rendering count indicator
  const pendingJobsCount = jobs.filter(
    (j) => j.status === 'pending' || j.status === 'processing'
  ).length;

  return (
    <div className="w-full min-h-screen">
      <PhoneContainer theme={theme} setTheme={setTheme}>
        
        {/* Dynamic Island System Floating Overlay Toast Notification Banner */}
        {toastMessage && (
          <div className="absolute top-1 left-4 right-4 bg-slate-900/90 hover:bg-slate-900 border border-sky-400/25 p-2 px-3 rounded-2xl flex items-center gap-2.5 shadow-2xl z-50 text-[10px] text-sky-305 font-bold animate-pulse">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping shrink-0" />
            <span className="flex-1 text-left line-clamp-1">{toastMessage}</span>
          </div>
        )}

        {/* Dynamic Main App Tab Content Views routing */}
        <div className="flex-1 overflow-hidden relative">
          
          {/* View Tab 1: Discover / Public Feed */}
          {activeTab === 'discover' && (
            <DiscoverTab
              items={galleryItems}
              setItems={setGalleryItems}
              onUsePrompt={handleUsePrompt}
              theme={theme}
            />
          )}

          {/* View Tab 2: Generator Workspace console */}
          {activeTab === 'generate' && (
            <GenerateTab
              initialPrompt={formPrompt}
              setInitialPrompt={setFormPrompt}
              initialType={formType}
              setInitialType={setFormType}
              initialModel={formModel}
              setInitialModel={setFormModel}
              initialAspectRatio={formAspectRatio}
              setInitialAspectRatio={setFormAspectRatio}
              onSynthesize={handleSynthesizeLaunch}
              userCredits={userCredits}
              theme={theme}
            />
          )}

          {/* View Tab 3: Chat Assistant with Agnes GPT */}
          {activeTab === 'assistant' && (
            <AssistantTab
              chatMessages={chatMessages}
              setChatMessages={setChatMessages}
              onImportPrompt={handleImportPromptFromChatClient}
              theme={theme}
            />
          )}

          {/* View Tab 4: My Personal Creations portfolio list */}
          {activeTab === 'creations' && (
            <CreationsTab
              jobs={jobs}
              setJobs={setJobs}
              theme={theme}
            />
          )}

          {/* View Tab 5: Profile manager and Credits center */}
          {activeTab === 'profile' && (
            <ProfileTab
              userCredits={userCredits}
              setUserCredits={setUserCredits}
              theme={theme}
            />
          )}
        </div>

        {/* FIXED APP BAR: Bottom Mobile Nav Menu */}
        <div className={`h-14 border-t px-2.5 flex items-center justify-around shrink-0 z-40 relative select-none ${
          theme === 'dark' ? 'bg-slate-950 border-slate-900' : 'bg-white border-slate-150'
        }`}>
          
          {/* Tab Button 1: Discover */}
          <button
            onClick={() => setActiveTab('discover')}
            className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${
              activeTab === 'discover'
                ? 'text-sky-400 font-extrabold translate-y-[-1px]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Compass className={`w-4 h-4 ${activeTab === 'discover' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Discover</span>
          </button>

          {/* Tab Button 2: Generate Engine console */}
          <button
            onClick={() => setActiveTab('generate')}
            className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${
              activeTab === 'generate'
                ? 'text-sky-400 font-extrabold translate-y-[-1px]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Sparkles className={`w-4 h-4 ${activeTab === 'generate' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Engine</span>
          </button>

          {/* Tab Button 3: AI Assistant chatbot */}
          <button
            onClick={() => setActiveTab('assistant')}
            className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${
              activeTab === 'assistant'
                ? 'text-sky-400 font-extrabold translate-y-[-1px]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <MessageSquare className={`w-4 h-4 ${activeTab === 'assistant' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">AI Coach</span>
          </button>

          {/* Tab Button 4: My Creations */}
          <button
            onClick={() => setActiveTab('creations')}
            className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all relative ${
              activeTab === 'creations'
                ? 'text-sky-400 font-extrabold translate-y-[-1px]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <FolderHeart className={`w-4 h-4 ${activeTab === 'creations' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Creations</span>

            {/* In-Progress GPU tasks badge indicators count count */}
            {pendingJobsCount > 0 && (
              <span className="absolute top-1 right-3.5 px-1 bg-sky-505 border border-slate-950 text-slate-950 font-black text-[7px] font-mono rounded-full animate-bounce">
                {pendingJobsCount}
              </span>
            )}
          </button>

          {/* Tab Button 5: Profiles */}
          <button
            onClick={() => setActiveTab('profile')}
            className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${
              activeTab === 'profile'
                ? 'text-sky-400 font-extrabold translate-y-[-1px]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <User className={`w-4 h-4 ${activeTab === 'profile' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Creator</span>
          </button>

        </div>
      </PhoneContainer>
    </div>
  );
}
