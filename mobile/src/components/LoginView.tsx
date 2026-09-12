/**
 * 登录视图组件
 */
import React, { useState } from 'react';
import { LogIn, UserPlus, Loader2, Sparkles } from 'lucide-react';
import { login, register, getMe } from '../api/auth';
import { setToken } from '../api/client';
import { User } from '../types';

interface LoginViewProps {
  onLoginSuccess: (user: User) => void;
}

export default function LoginView({ onLoginSuccess }: LoginViewProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // 登录或注册获取Token
      const tokenResp = mode === 'login'
        ? await login({ username, password })
        : await register({ username, password, email: email || undefined });

      setToken(tokenResp.access_token);

      // 获取用户信息
      const user = await getMe();
      onLoginSuccess(user);
    } catch (err: any) {
      setError(err.message || '操作失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col items-center justify-center p-6 text-white">
      {/* Logo */}
      <div className="mb-8 text-center">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30 mb-3">
          <Sparkles className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-xl font-bold tracking-tight">
          Agnes<span className="text-blue-500">AI</span>
        </h1>
        <p className="text-[10px] text-slate-500 font-mono mt-1 uppercase tracking-wider">
          Mobile Console
        </p>
      </div>

      {/* 模式切换 */}
      <div className="flex bg-[#161920] border border-white/5 p-0.5 rounded-xl mb-5 w-full max-w-xs">
        <button
          onClick={() => setMode('login')}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded-lg transition-all ${
            mode === 'login' ? 'bg-blue-500 text-slate-950' : 'text-slate-400'
          }`}
        >
          登录
        </button>
        <button
          onClick={() => setMode('register')}
          className={`flex-1 py-1.5 text-[10px] font-bold rounded-lg transition-all ${
            mode === 'register' ? 'bg-blue-500 text-slate-950' : 'text-slate-400'
          }`}
        >
          注册
        </button>
      </div>

      {/* 表单 */}
      <div className="w-full max-w-xs space-y-3">
        <div>
          <label className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block font-mono mb-1">
            用户名
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入用户名"
            className="w-full text-xs py-2 px-3 rounded-xl bg-[#161920] border border-white/5 text-slate-200 outline-none focus:border-blue-500/30"
          />
        </div>

        {mode === 'register' && (
          <div>
            <label className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block font-mono mb-1">
              邮箱（可选）
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full text-xs py-2 px-3 rounded-xl bg-[#161920] border border-white/5 text-slate-200 outline-none focus:border-blue-500/30"
            />
          </div>
        )}

        <div>
          <label className="text-[8.5px] font-bold text-slate-500 uppercase tracking-widest block font-mono mb-1">
            密码
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            className="w-full text-xs py-2 px-3 rounded-xl bg-[#161920] border border-white/5 text-slate-200 outline-none focus:border-blue-500/30"
          />
        </div>

        {error && (
          <div className="p-2 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[10px] rounded-lg text-center font-mono">
            {error}
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full py-2.5 bg-blue-500 text-slate-950 font-bold text-xs rounded-xl flex items-center justify-center gap-2 hover:scale-[1.01] active:scale-[0.99] transition-all shadow-md shadow-blue-500/30 disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : mode === 'login' ? (
            <LogIn className="w-3.5 h-3.5" />
          ) : (
            <UserPlus className="w-3.5 h-3.5" />
          )}
          {loading ? '处理中...' : mode === 'login' ? '登录' : '注册'}
        </button>
      </div>
    </div>
  );
}
