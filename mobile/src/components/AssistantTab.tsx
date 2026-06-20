import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, MessageSquare, PlusCircle, ArrowRight, CornerDownLeft, Bot } from 'lucide-react';
import { ChatMessage, GenType } from '../types';

interface AssistantTabProps {
  chatMessages: ChatMessage[];
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  onImportPrompt: (prompt: string, type: GenType) => void;
  theme: 'dark' | 'light';
}

export default function AssistantTab({ chatMessages, setChatMessages, onImportPrompt, theme }: AssistantTabProps) {
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll inside chat
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatMessages, isTyping]);

  // Suggested quick prompts cards list
  const suggestedIdeas = [
    { label: "🦊 Mystical Aurora Fox", concept: "A spirit fox steps through arctic aurora lights" },
    { label: "🌃 Retro-Cyber Tokyo", concept: "Slow camera orbit in retro futuristic neo Tokyo, rain reflections, neon flyers" },
    { label: "🍲 Ghibli Cozy Ramen", concept: "Warm cozy Ghibli style ramen stall inside a mystical tree, steaming bowls" }
  ];

  const handleSend = (textToSend = inputText) => {
    if (!textToSend.trim()) return;

    // 1. Add user message
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text: textToSend,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsTyping(true);

    // 2. Mock AI response after short delay
    setTimeout(() => {
      setIsTyping(false);

      // Create elegant prompt expansion according to the concept
      const concept = textToSend.toLowerCase();
      let responseText = '';
      let recommendedPrompt = '';

      if (concept.includes('fox') || concept.includes('spirit')) {
        responseText = "I've structured a magical fantasy prompt focused on the spiritual element. We'll utilize high-end volumetric lighting and a glowing particle dust effect to bring out that enchanted feeling.";
        recommendedPrompt = "A magical glowing spirit kitsune fox stepping out of an aurora portal in an enchanted glowing forest, ancient runes on the giant trees, sparkling golden pollen floating, mystical purple and pale aqua colors, detailed oil strokes, highly cinematic";
      } else if (concept.includes('ramen') || concept.includes('ghibli') || concept.includes('cozy')) {
        responseText = "Lovely! A cozy food setting looks best in an anime hand-drawn palette. I have curated highly vibrant watercolor sunset hues and steaming light physics similar to classic Ghibli / Kyoto Animation films.";
        recommendedPrompt = "A giant weathered warm tea stall peacefully under massive pink cherry blossom trees, steaming bowls on rustic wooden table, soft afternoon sun rays filtering, hand drawn lofi key visual, Kyoto Animation style";
      } else if (concept.includes('cyber') || concept.includes('neon') || concept.includes('retro')) {
        responseText = "Cyberpunk art needs extreme lighting contrast. Let's construct a prompt centered on high-tech gear, reflective rain-washed asphalt, and complementary cyan/magenta neon bars.";
        recommendedPrompt = "A sleek retro-futuristic hover sports car with glowing turquoise booster lights flying over a cyber-synthwave neon-lit highway at night, purple mist, vaporwave aesthetics, cinematic motion blur, 8k resolution";
      } else {
        // Generic smart expand
        responseText = `Excellent visual concept: "${textToSend}". I have engineered a professionally balanced diffusion prompt capturing rich textures, volumetric atmospheres, and cinematic styling.`;
        recommendedPrompt = `A stunning masterwork of ${textToSend}, highly detailed textures, dramatic lighting dynamics, atmospheric depths, soft organic coloring, intricate details, octane render, trending on artstation`;
      }

      const aiMsg: ChatMessage = {
        id: `msg-ai-${Date.now()}`,
        sender: 'agnes',
        text: responseText,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        suggestedPrompt: recommendedPrompt
      };

      setChatMessages((prev) => [...prev, aiMsg]);
    }, 1500);
  };

  return (
    <div id="assistant-tab" className="h-full flex flex-col pt-2 overflow-hidden select-none">
      
      {/* Tab Header (High Density Theme compliance) */}
      <div className="px-4 pb-2 border-b border-white/5 flex justify-between items-center shrink-0 mt-1 text-left">
        <div>
          <h2 className="text-sm font-bold tracking-tight text-white flex items-center gap-1.5">
            <span className="w-2 h-2 rounded bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)] flex shrink-0"></span>
            Agnes<span className="text-blue-500">AI</span>
            <span className="text-[10px] text-slate-500 font-mono font-normal ml-0.5">/ CO-PILOT</span>
          </h2>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">Conversational prompt Architect</p>
        </div>

        <div className="text-[8px] font-mono text-slate-400 bg-[#161920] border border-white/5 px-2.5 py-0.5 rounded-md font-bold">
          ONLINE
        </div>
      </div>

      {/* Chat Messages Scrolling viewport */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-none"
      >
        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col max-w-[85%] ${
              msg.sender === 'user' ? 'ml-auto items-end' : 'items-start text-left'
            }`}
          >
            {/* Timestamp */}
            <span className="text-[8px] text-slate-500 mb-1 font-mono">{msg.createdAt}</span>

            {/* Message bubble */}
            <div
              className={`p-2.5 rounded-xl text-[10.5px] leading-relaxed ${
                msg.sender === 'user'
                  ? 'bg-blue-500 text-slate-950 font-bold rounded-tr-none shadow-[0_0_8px_rgba(59,130,246,0.25)]'
                  : 'bg-[#161920] border border-white/5 text-slate-200 rounded-tl-none'
              }`}
            >
              {msg.text}
            </div>

            {/* Special Prompt Blueprint Card attachment (if generated by Agnes) */}
            {msg.sender === 'agnes' && msg.suggestedPrompt && (
              <div className="w-full mt-2.5 p-3 rounded-xl bg-[#161920] border border-white/5 text-left space-y-2 shadow-xl shrink-0">
                <div className="flex items-center gap-1.5 text-blue-400 text-[8px] font-black uppercase tracking-wider font-mono">
                  <Sparkles className="w-3 h-3 animate-pulse text-indigo-400" />
                  Agnes Core Render Formula
                </div>
                
                <p className="text-[9.5px] text-slate-300 font-mono leading-relaxed bg-slate-950/70 p-2 rounded-lg border border-white/5 select-text">
                  {msg.suggestedPrompt}
                </p>

                <button
                  onClick={() => onImportPrompt(
                    msg.suggestedPrompt!,
                    msg.suggestedPrompt?.toLowerCase().includes('car') || msg.suggestedPrompt?.toLowerCase().includes('flight') ? 'video' : 'image'
                  )}
                  className="w-full py-1.5 bg-blue-500 text-slate-950 font-extrabold text-[9px] rounded-lg flex items-center justify-center gap-1 transition-all hover:scale-[1.01] active:scale-[0.99] uppercase shadow-[0_0_10px_rgba(59,130,246,0.2)]"
                >
                  Load Formula to Engine
                  <ArrowRight className="w-3 h-3 text-slate-950" />
                </button>
              </div>
            )}
          </div>
        ))}

        {/* Typing bubble simulator */}
        {isTyping && (
          <div className="flex flex-col max-w-[85%] items-start text-left">
            <span className="text-[8px] text-slate-500 mb-1 font-mono">Agnes...</span>
            <div className="py-2.5 px-3 bg-[#161920] border border-white/5 text-slate-300 rounded-xl rounded-tl-none flex items-center space-x-1">
              <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
      </div>

      {/* Suggested Quick Question Suggestions row */}
      {chatMessages.length === 1 && (
        <div className="px-4 pb-2.5 text-left space-y-1.5 select-none shrink-0 bg-[#0F1115] pt-1.5 border-t border-white/5">
          <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest block font-mono">Suggested seed-gates</span>
          <div className="flex space-x-2 overflow-x-auto pb-1 scrollbar-none">
            {suggestedIdeas.map((idea, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSend(idea.concept)}
                className="flex-shrink-0 px-2.5 py-1.5 bg-[#161920] border border-white/5 hover:border-blue-500/25 rounded-md text-[9px] text-slate-300 font-bold transition-all active:scale-[0.98]"
              >
                {idea.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Fixed Chat Input Form Box */}
      <div className="p-2.5 bg-[#0F1115] border-t border-white/5 shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="relative flex items-center"
        >
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Query layout description..."
            className="w-full text-[10.5px] py-1.5 px-3.5 pr-12 rounded-xl bg-slate-950 border border-white/5 text-slate-200 placeholder-slate-500 outline-none focus:border-blue-500/30"
          />
          <button
            type="submit"
            disabled={!inputText.trim()}
            className={`absolute right-1.5 p-1 px-2 rounded-lg text-xs font-black transition-all ${
              inputText.trim()
                ? 'bg-blue-500 text-slate-950 opacity-100'
                : 'bg-[#161920] text-slate-600 opacity-60'
            }`}
          >
            <Send className="w-3 h-3 text-slate-950" />
          </button>
        </form>
      </div>
    </div>
  );
}
