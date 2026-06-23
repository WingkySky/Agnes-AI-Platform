/**
 * Types for Agnes AI Platform Mobile App Designer
 */

export type AppTab = 'discover' | 'generate' | 'assistant' | 'creations' | 'profile';

/**
 * 用户信息类型
 */
export interface User {
  id: number;
  username: string;
  email: string | null;
  avatar_url: string | null;
  credits: number;
  role: string;
  is_active: boolean;
  is_admin: boolean;
}

export type GenType = 'image' | 'video';

export interface AIModel {
  id: string;
  name: string;
  version: string;
  description: string;
  type: GenType | 'both';
  badge?: string;
  speed: string;
}

export interface AspectRatio {
  id: string;
  label: string;
  value: string;
  icon: string;
}

export interface GenerationJob {
  id: string;
  prompt: string;
  negativePrompt?: string;
  type: GenType;
  modelId: string;
  aspectRatio: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  resultUrl?: string;
  duration?: number; // for video
  motionStrength?: number; // for video
  cameraMovement?: string; // for video
  createdAt: string;
}

export interface GalleryItem {
  id: string;
  title: string;
  prompt: string;
  negativePrompt?: string;
  type: GenType;
  author: {
    name: string;
    avatar: string;
    tier: 'Pro' | 'VIP' | 'Free';
  };
  modelName: string;
  aspectRatio: string;
  likes: number;
  views: number;
  imageUrl: string;
  videoUrl?: string;
  isLiked?: boolean;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agnes';
  text: string;
  createdAt: string;
  suggestedPrompt?: string;
}

export interface StylePreset {
  id: string;
  name: string;
  image: string;
  promptSuffix: string;
}
