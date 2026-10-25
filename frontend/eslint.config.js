// =====================================================
// ESLint flat config
// 策略：正确性优先、风格类不查（引号/缩进/行长交给 TS 与既有代码习惯）
// Vue 用 essential（防错误集）；TS 用 recommended；存量告警爆炸的规则按项目现实关闭
// =====================================================
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'

export default defineConfigWithVueTs(
  {
    ignores: ['dist/**', 'coverage/**'],
  },
  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  {
    files: ['**/*.ts', '**/*.vue'],
    rules: {
      // views 下单名词组件是既有惯例
      'vue/multi-word-component-names': 'off',
      // 项目现实：any 大量存在于 AI 生成代码，类型正确性由 vue-tsc 把关，lint 不再重复约束
      '@typescript-eslint/no-explicit-any': 'off',
      // ts-ignore 必须带说明文字（存量三处均带）
      '@typescript-eslint/ban-ts-comment': ['error', { 'ts-ignore': 'allow-with-description' }],
      // 6/6 命中均为合法惯用法（Pinia 响应式追踪读取 / 三元表达式），规则信噪比不足，关闭
      '@typescript-eslint/no-unused-expressions': 'off',
      // `_` 前缀 = 有意占位（未用回调参数/预留变量）；ignoreRestSiblings 兼容 omit 解构惯用法
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrors: 'none',
          ignoreRestSiblings: true,
        },
      ],
    },
  },
)
