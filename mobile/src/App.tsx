/**
 * Agnes AI Platform Mobile App
 * 移动端应用主入口
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Compass, Sparkles, MessageSquare, FolderHeart, User, Loader2 } from 'lucide-react';
import PhoneContainer from './components/PhoneContainer';
import DiscoverTab from './components/DiscoverTab';
import GenerateTab from './components/GenerateTab';
import AssistantTab from './components/AssistantTab';
import CreationsTab from './components/CreationsTab';
import ProfileTab from './components/ProfileTab';
import LoginView from './components/LoginView';

import { AppTab, GenType, GenerationJob, User } from './types';
import { INITIAL_GALLERY_ITEMS, INITIAL_CHAT_MESSAGES } from './data';
import { getMe, getCredits } from './api/auth';
import { createImageTask, getImageTaskStatus } from './api/images';
import { createVideoTask, getVideoStatus } from './api/videos';
import { getToken } from './api/client';

export default function App() {
  // 登录状态
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [userCredits, setUserCredits] = useState(0);

  const [activeTab, setActiveTab] = useState<AppTab>('discover');
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [galleryItems, setGalleryItems] = useState(INITIAL_GALLERY_ITEMS);
  const [chatMessages, setChatMessages] = useState(INITIAL_CHAT_MESSAGES);

  // 生成任务队列
  const [jobs, setJobs] = useState<GenerationJob[]>([]);

  // 表单状态
  const [formPrompt, setFormPrompt] = useState('');
  const [formType, setFormType] = useState<GenType>('image');
  const [formModel, setFormModel] = useState('agnes-vision-ultra');
  const [formAspectRatio, setFormAspectRatio] = useState('3:4');

  // Toast通知
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // 初始化检查登录状态
  useEffect(() => {
    const checkAuth = async () => {
      const token = getToken();
      if (!token) {
        setIsLoading(false);
        return;
      }
      try {
        const userInfo = await getMe();
        setUser(userInfo);
        setUserCredits(userInfo.credits);
        setIsLoggedIn(true);
      } catch (err) {
        // token无效，清除
        localStorage.removeItem('agnes_mobile_auth_token');
      } finally {
        setIsLoading(false);
      }
    };
    checkAuth();
  }, []);

  // 监听登出事件
  useEffect(() => {
    const handleLogout = () => {
      setIsLoggedIn(false);
      setUser(null);
      setUserCredits(0);
      setJobs([]);
    };
    window.addEventListener('mobile:logout', handleLogout);
    return () => window.removeEventListener('mobile:logout', handleLogout);
  }, []);

  // 轮询任务状态
  useEffect(() => {
    const activeJobs = jobs.filter(j => j.status === 'pending' || j.status === 'processing');
    if (activeJobs.length === 0) return;

    const pollInterval = setInterval(async () => {
      setJobs(prevJobs => {
        let hasUpdate = false;
        const next = [...prevJobs];

        Promise.all(activeJobs.map(async (job) => {
          try {
            if (job.type === 'image') {
              const status = await getImageTaskStatus(job.id);
              if (status.status === 'success' || status.status === 'completed') {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1) {
                  next[idx] = { ...next[idx], status: 'completed', progress: 100, resultUrl: status.result_url || status.url };
                  hasUpdate = true;
                }
              } else if (status.status === 'failed') {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1) {
                  next[idx] = { ...next[idx], status: 'failed' };
                  hasUpdate = true;
                }
              } else {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1 && status.progress !== undefined) {
                  next[idx] = { ...next[idx], progress: status.progress, status: 'processing' };
                  hasUpdate = true;
                }
              }
            } else {
              const status = await getVideoStatus(job.id);
              if (status.status === 'success') {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1) {
                  next[idx] = { ...next[idx], status: 'completed', progress: 100, resultUrl: status.video_url };
                  hasUpdate = true;
                }
              } else if (status.status === 'failed') {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1) {
                  next[idx] = { ...next[idx], status: 'failed' };
                  hasUpdate = true;
                }
              } else {
                const idx = next.findIndex(j => j.id === job.id);
                if (idx !== -1 && status.progress !== undefined) {
                  next[idx] = { ...next[idx], progress: status.progress, status: 'processing' };
                  hasUpdate = true;
                }
              }
            }
          } catch (err) {
            console.error('轮询失败:', job.id, err);
          }
        }));

        return hasUpdate ? next : prevJobs;
      });
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [jobs]);

  // 刷新积分
  const refreshCredits = useCallback(async () => {
    try {
      const resp = await getCredits();
      setUserCredits(resp.credits);
      if (user) {
        setUser({ ...user, credits: resp.credits });
      }
    } catch (err) {
      console.error('刷新积分失败:', err);
    }
  }, [user]);

  // Toast提示
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // 登录成功回调
  const handleLoginSuccess = (userInfo: User) => {
    setUser(userInfo);
    setUserCredits(userInfo.credits);
    setIsLoggedIn(true);
  };

  // 从Discover使用prompt
  const handleUsePrompt = (prompt: string, type: GenType, modelName: string, aspectRatio: string) => {
    setFormPrompt(prompt);
    setFormType(type);
    setFormModel(type === 'image' ? 'agnes-vision-ultra' : 'agnes-motion-cinematic');
    setFormAspectRatio(aspectRatio);
    setActiveTab('generate');
    showToast('Prompt settings applied!');
  };

  // 从聊天导入prompt
  const handleImportPromptFromChat = (prompt: string, type: GenType) => {
    setFormPrompt(prompt);
    setFormType(type);
    setFormModel(type === 'image' ? 'agnes-vision-ultra' : 'agnes-motion-cinematic');
    setFormAspectRatio('3:4');
    setActiveTab('generate');
    showToast('AI prompt exported!');
  };

  // 发起生成任务
  const handleSynthesizeLaunch = async (
    prompt: string,
    type: GenType,
    modelId: string,
    aspectRatio: string,
    videoConfig?: { duration: number; motionStrength: number; cameraMovement: string }
  ) => {
    const cost = type === 'image' ? 2 : 5;
    if (userCredits < cost) {
      showToast('Insufficient credits!');
      return;
    }

    try {
      let taskId: string;
      if (type === 'image') {
        // 图片生成
        const resp = await createImageTask({
          prompt,
          model: modelId,
          size: aspectRatio === '1:1' ? '1024x1024' : aspectRatio === '3:4' ? '1024x1366' : '1366x1024',
          aspect_ratio: aspectRatio,
          response_format: 'url',
        });
        taskId = resp.task_id;
      } else {
        // 视频生成
        const resp = await createVideoTask({
          prompt,
          model: modelId,
          aspect_ratio: aspectRatio,
          seconds: videoConfig?.duration || 4,
        });
        taskId = resp.task_id;
      }

      // 创建新任务
      const newJob: GenerationJob = {
        id: taskId,
        prompt,
        type,
        modelId,
        aspectRatio,
        status: 'pending',
        progress: 0,
        createdAt: new Date().toLocaleString(),
        ...(type === 'video' && videoConfig ? {
          duration: videoConfig.duration,
          motionStrength: videoConfig.motionStrength,
          cameraMovement: videoConfig.cameraMovement,
        } : {}),
      };

      setJobs(prev => [newJob, ...prev]);
      setUserCredits(prev => prev - cost);
      setActiveTab('creations');
      showToast('GPU Queue assigned!');
    } catch (err: any) {
      showToast(err.message || 'Generation failed!');
    }
  };

  // 活跃任务数
  const pendingJobsCount = jobs.filter(j => j.status === 'pending' || j.status === 'processing').length;

  // 加载中
  if (isLoading) {
    return (
      <div className="w-full min-h-screen bg-[#0F1115] flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  // 未登录显示登录页
  if (!isLoggedIn) {
    return (
      <div className="w-full min-h-screen bg-[#0F1115]">
        <LoginView onLoginSuccess={handleLoginSuccess} />
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen">
      <PhoneContainer theme={theme} setTheme={setTheme}>
        {/* Toast通知 */}
        {toastMessage && (
          <div className="absolute top-1 left-4 right-4 bg-slate-900/90 border border-sky-400/25 p-2 px-3 rounded-2xl flex items-center gap-2.5 shadow-2xl z-50 text-[10px] text-sky-305 font-bold animate-pulse">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping shrink-0" />
            <span className="flex-1 text-left line-clamp-1">{toastMessage}</span>
          </div>
        )}

        {/* Tab内容 */}
        <div className="flex-1 overflow-hidden relative">
          {activeTab === 'discover' && (
            <DiscoverTab items={galleryItems} setItems={setGalleryItems} onUsePrompt={handleUsePrompt} theme={theme} />
          )}
          {activeTab === 'generate' && (
            <GenerateTab
              initialPrompt={formPrompt} setInitialPrompt={setFormPrompt}
              initialType={formType} setInitialType={setFormType}
              initialModel={formModel} setInitialModel={setFormModel}
              initialAspectRatio={formAspectRatio} setInitialAspectRatio={setFormAspectRatio}
              onSynthesize={handleSynthesizeLaunch}
              userCredits={userCredits}
              theme={theme}
            />
          )}
          {activeTab === 'assistant' && (
            <AssistantTab
              chatMessages={chatMessages} setChatMessages={setChatMessages}
              onImportPrompt={handleImportPromptFromChat}
              theme={theme}
            />
          )}
          {activeTab === 'creations' && (
            <CreationsTab jobs={jobs} setJobs={setJobs} theme={theme} />
          )}
          {activeTab === 'profile' && (
            <ProfileTab
              user={user}
              userCredits={userCredits} setUserCredits={setUserCredits}
              onLogout={() => {
                localStorage.removeItem('agnes_mobile_auth_token');
                setIsLoggedIn(false);
                setUser(null);
              }}
              theme={theme}
            />
          )}
        </div>

        {/* 底部导航 */}
        <div className={`h-14 border-t px-2.5 flex items-center justify-around shrink-0 z-40 relative select-none ${
          theme === 'dark' ? 'bg-slate-950 border-slate-900' : 'bg-white border-slate-150'
        }`}>
          <button onClick={() => setActiveTab('discover')} className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${activeTab === 'discover' ? 'text-sky-400 font-extrabold translate-y-[-1px]' : 'text-slate-500 hover:text-slate-300'}`}>
            <Compass className={`w-4 h-4 ${activeTab === 'discover' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Discover</span>
          </button>
          <button onClick={() => setActiveTab('generate')} className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${activeTab === 'generate' ? 'text-sky-400 font-extrabold translate-y-[-1px]' : 'text-slate-500 hover:text-slate-300'}`}>
            <Sparkles className={`w-4 h-4 ${activeTab === 'generate' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Engine</span>
          </button>
          <button onClick={() => setActiveTab('assistant')} className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${activeTab === 'assistant' ? 'text-sky-400 font-extrabold translate-y-[-1px]' : 'text-slate-500 hover:text-slate-300'}`}>
            <MessageSquare className={`w-4 h-4 ${activeTab === 'assistant' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">AI Coach</span>
          </button>
          <button onClick={() => setActiveTab('creations')} className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all relative ${activeTab === 'creations' ? 'text-sky-400 font-extrabold translate-y-[-1px]' : 'text-slate-500 hover:text-slate-300'}`}>
            <FolderHeart className={`w-4 h-4 ${activeTab === 'creations' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Creations</span>
            {pendingJobsCount > 0 && (
              <span className="absolute top-1 right-3.5 px-1 bg-sky-505 border border-slate-950 text-slate-950 font-black text-[7px] font-mono rounded-full animate-bounce">
                {pendingJobsCount}
              </span>
            )}
          </button>
          <button onClick={() => setActiveTab('profile')} className={`flex-1 py-1 flex flex-col items-center justify-center space-y-0.5 outline-none transition-all ${activeTab === 'profile' ? 'text-sky-400 font-extrabold translate-y-[-1px]' : 'text-slate-500 hover:text-slate-300'}`}>
            <User className={`w-4 h-4 ${activeTab === 'profile' ? 'stroke-[2.5px]' : 'stroke-[1.8px]'}`} />
            <span className="text-[8px] font-bold tracking-tight uppercase">Creator</span>
          </button>
        </div>
      </PhoneContainer>
    </div>
  );
}
