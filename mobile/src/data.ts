import { GalleryItem, AIModel, AspectRatio, StylePreset } from './types';

export const AI_MODELS: AIModel[] = [
  {
    id: 'agnes-vision-ultra',
    name: 'Agnes Vision v2.5 Ultra',
    version: '2.5.0-ultra',
    description: 'Our flagship photo-realistic image generator. Excels at detail, lighting, and anatomy.',
    type: 'image',
    badge: 'Pro Tier',
    speed: '4.2s Base-Gen'
  },
  {
    id: 'agnes-flux-speed',
    name: 'Agnes Flux Lightning',
    version: '1.2.0-speed',
    description: 'Super-fast, crisp digital art & creative illustrations with amazing prompt adherence.',
    type: 'image',
    badge: 'Fast',
    speed: '1.5s Speed-Gen'
  },
  {
    id: 'agnes-anime-delight',
    name: 'Agnes Anime Delight',
    version: '3.1.0-art',
    description: 'Perfected model for anime, illustration, manga ink, and cartoon visual styles.',
    type: 'image',
    badge: 'Art Focus',
    speed: '3.0s Fine-Tune'
  },
  {
    id: 'agnes-motion-cinematic',
    name: 'Agnes Motion-Cinema v2',
    version: '2.0.2-motion',
    description: 'High-fidelity video synthesis. Impeccable temporal stability & realistic physics.',
    type: 'video',
    badge: 'HD Video',
    speed: '12.0s Motion-Gen'
  },
  {
    id: 'agnes-anime-motion',
    name: 'Agnes Anime Motion v1',
    version: '1.0.5-motion',
    description: 'Transform your illustrations or prompts into fluid, beautifully cel-shaded 2D anime cutscenes.',
    type: 'video',
    badge: 'Anime Motion',
    speed: '15.0s Dynamic-Gen'
  }
];

export const ASPECT_RATIOS: AspectRatio[] = [
  { id: '1:1', label: 'Square', value: '1:1', icon: 'Square' },
  { id: '9:16', label: 'Portrait', value: '9:16', icon: 'Smartphone' },
  { id: '3:4', label: 'Standard', value: '3:4', icon: 'RectangleVertical' },
  { id: '4:3', label: 'Classic', value: '4:3', icon: 'Tv' },
  { id: '16:9', label: 'Widescreen', value: '16:9', icon: 'Monitor' }
];

export const STYLE_PRESETS: StylePreset[] = [
  {
    id: 'cinematic',
    name: 'Cinematic Photo',
    image: 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', highly realistic, cinematic lighting, 85mm lens, depth of field, sharp focus, 8k resolution'
  },
  {
    id: 'cyberpunk',
    name: 'Cyberpunk Neon',
    image: 'https://images.unsplash.com/photo-1515621061946-eff1c2a352bd?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', cyberpunk style, glowing neon signs, rainy streets, futuristic tech atmosphere, pink and cyan hues, highly detailed'
  },
  {
    id: 'fantasy',
    name: 'Ethereal Fantasy',
    image: 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', magical fantasy art, mystical glow, dreamy fairytale setting, watercolor elements, golden dust, octane render'
  },
  {
    id: 'anime',
    name: 'Anime Aesthetic',
    image: 'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', modern anime illustration, beautiful key visual, high fidelity, vibrant sunset colors, Kyoto animation style'
  },
  {
    id: 'pixel-art',
    name: 'Lofi Pixel Art',
    image: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', gorgeous pixel art, 16-bit lofi styling, warm cozy ambient colors, nostalgic atmosphere, sharp pixels'
  },
  {
    id: 'surrealism',
    name: 'Mystic Surrealist',
    image: 'https://images.unsplash.com/photo-1541701494587-cb58502866ab?w=200&auto=format&fit=crop&q=80',
    promptSuffix: ', surreal oil painting style, hyper-detailed bizarre geometry, Salvador Dali inspiration, cosmic stars, dreamy'
  }
];

export const INITIAL_GALLERY_ITEMS: GalleryItem[] = [
  {
    id: 'cyberpunk-maiden',
    title: 'Cyberpunk Wing Pilot',
    prompt: 'A close up cinematic portrait of a cyberpunk female pilot with soft neon facial markings, reflective visor, intricate cybernetic headwear, wearing a vintage bomber jacket, glowing blue and pink ambient light, high-end photography, cinematic, 8k resolution, detailed texture',
    type: 'image',
    author: {
      name: 'Agnes_CreatorX',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80',
      tier: 'Pro'
    },
    modelName: 'Agnes Vision v2.5 Ultra',
    aspectRatio: '3:4',
    likes: 852,
    views: 3410,
    imageUrl: '/src/assets/images/cyber_girl_portrait_1781971382057.jpg',
    isLiked: false
  },
  {
    id: 'mythic-crystalline-temple',
    title: 'Ethereal Floating Sanctuary',
    prompt: 'A breathtaking fantasy landscape of an ancient floating stone temple carved into a massive levitating crystal rock, cascading waterfalls pouring down into infinite space, golden sunrays filtering through fluffy pink clouds, majestic birds soaring, ethereal and dreamy atmosphere, unreal engine 5 render, highly detailed, masterpieces',
    type: 'image',
    author: {
      name: 'LotusBloom',
      avatar: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=100&auto=format&fit=crop&q=80',
      tier: 'VIP'
    },
    modelName: 'Agnes Vision v2.5 Ultra',
    aspectRatio: '3:4',
    likes: 1204,
    views: 4890,
    imageUrl: '/src/assets/images/floating_temple_fantasy_1781971398624.jpg',
    isLiked: true
  },
  {
    id: 'retro-super-hovercar',
    title: 'Neon Drift 2088',
    prompt: 'A sleek retro-futuristic black hover sports car with glowing turquoise booster lights flying over a cyber-synthwave neon-lit highway at night, towering holographic buildings in the background, purple mist, vaporwave aesthetics, motion blur, extremely high resolution, cinematic framing',
    type: 'video',
    author: {
      name: 'Velo_Synth',
      avatar: 'https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=100&auto=format&fit=crop&q=80',
      tier: 'Pro'
    },
    modelName: 'Agnes Motion-Cinema v2',
    aspectRatio: '16:9',
    likes: 947,
    views: 2831,
    imageUrl: '/src/assets/images/retro_cyber_car_1781971412978.jpg',
    videoUrl: 'https://assets.mixkit.co/videos/preview/mixkit-cyberpunk-neon-city-street-at-night-42571-large.mp4',
    isLiked: false
  },
  {
    id: 'aurora-fox',
    title: 'Cosmic Kitsune Guardian',
    prompt: 'A magical glowing spirit kitsune fox stepping out of an aurora portal in an enchanted glowing forest, ancient runes on the giant trees, sparkling golden pollen floating, mystical purple and pale aqua colors, detailed oil strokes',
    type: 'image',
    author: {
      name: 'Kitsune_Art',
      avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&auto=format&fit=crop&q=80',
      tier: 'Free'
    },
    modelName: 'Agnes Flux Lightning',
    aspectRatio: '1:1',
    likes: 412,
    views: 1540,
    imageUrl: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80',
    isLiked: false
  },
  {
    id: 'cyber-city-mech',
    title: 'Guardian Unit RX-7',
    prompt: 'A giant weathered warm mech standing peacefully under massive pink cherry blossom trees in a retro neo-Tokyo street, soft afternoon sun rays filter through petals, children playing near the foot, watercolor anime cinematic',
    type: 'image',
    author: {
      name: 'MechaMinds',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&auto=format&fit=crop&q=80',
      tier: 'Pro'
    },
    modelName: 'Agnes Anime Delight',
    aspectRatio: '1:1',
    likes: 723,
    views: 2901,
    imageUrl: 'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=600&auto=format&fit=crop&q=80',
    isLiked: false
  },
  {
    id: 'liquid-sculpture',
    title: 'Liquid Gold Cosmos',
    prompt: 'Dynamic splashes of shining fluid gold forming nested spherical orbits in interstellar void, nebula clusters, vibrant stars, hyper-realistic reflections on the golden curves, surreal 3D modeling',
    type: 'video',
    author: {
      name: 'Aether_Gaze',
      avatar: 'https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=100&auto=format&fit=crop&q=80',
      tier: 'VIP'
    },
    modelName: 'Agnes Motion-Cinema v2',
    aspectRatio: '16:9',
    likes: 1580,
    views: 5210,
    imageUrl: 'https://images.unsplash.com/photo-1541701494587-cb58502866ab?w=600&auto=format&fit=crop&q=80',
    videoUrl: 'https://assets.mixkit.co/videos/preview/mixkit-flying-through-a-universe-of-glowing-stars-41804-large.mp4',
    isLiked: false
  }
];

export const INITIAL_CHAT_MESSAGES = [
  {
    id: 'welcome',
    sender: 'agnes' as const,
    text: "Hello! I am your Agnes AI prompt strategist. Give me a simple concept (e.g., 'a glowing mushroom forest') and I will craft a rich, professional generation prompt matching modern diffusion configurations. Feel free to ask anything!",
    createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
];
