import type { IconName } from './components/Icon';

export type PageId =
  | 'home'
  | 'assistant'
  | 'agents'
  | 'automations'
  | 'workspace'
  | 'more'
  | 'tasks'
  | 'settings'
  | 'bank'
  | 'interview'
  | 'reports'
  | 'review';

export interface PageInfo {
  label: string;
  icon: IconName;
  milestone: string;
  description: string;
}

export const PAGES: Record<PageId, PageInfo> = {
  home: {
    label: '新建任务',
    icon: 'home',
    milestone: '',
    description: '',
  },
  assistant: {
    label: '助理',
    icon: 'bot',
    milestone: 'M1 / M2',
    description: '内置面试题整理与 AI 面试官 Agent。',
  },
  agents: {
    label: '专家 · 技能 · 连接器',
    icon: 'layers',
    milestone: 'M3',
    description: '自定义 Agent、工具策略与本地 stdio MCP。',
  },
  automations: {
    label: '定时任务',
    icon: 'clock',
    milestone: 'P0 之外',
    description: '后台调度不在 P0 范围，当前只保留信息架构入口。',
  },
  workspace: {
    label: '资料库',
    icon: 'book',
    milestone: 'M1 Task 04',
    description: '关联目录、选择材料并保留来源快照。',
  },
  more: {
    label: '更多',
    icon: 'home',
    milestone: '共用导航',
    description: '题库、面试、报告与复习入口。',
  },
  tasks: {
    label: '任务记录',
    icon: 'history',
    milestone: 'M1 Task 02～03',
    description: '找回任务、检查点和已保存成果。',
  },
  settings: {
    label: '设置与工具',
    icon: 'settings',
    milestone: 'M1 Task 05 / M3',
    description: '模型、语音、MCP 与默认参数。',
  },
  bank: {
    label: '面试题库',
    icon: 'book',
    milestone: 'M1 Task 06～07',
    description: '筛选、查看来源并手选题目。',
  },
  interview: {
    label: 'AI 面试官',
    icon: 'bot',
    milestone: 'M2',
    description: '文字训练、追问、反馈与报告。',
  },
  reports: {
    label: '面试记录',
    icon: 'history',
    milestone: 'M2',
    description: '回看已归档的问题、原回答和笔记。',
  },
  review: {
    label: '复习清单',
    icon: 'check',
    milestone: 'M2',
    description: '先回忆再核对，保留自评与辅助记录。',
  },
};

export const PRIMARY_PAGES: PageId[] = [
  'home',
  'assistant',
  'agents',
  'automations',
  'workspace',
  'more',
];

export const MORE_PAGES: PageId[] = ['bank', 'interview', 'reports', 'review', 'agents'];
