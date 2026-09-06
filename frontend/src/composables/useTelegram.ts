import { ref, onMounted } from 'vue';
import type { TelegramWebAppUser } from '@/types/telegram'

interface TelegramWebAppLike {
  initDataUnsafe?: {
    user?: TelegramWebAppUser
    [key: string]: unknown
  }
  ready: () => void
  setHeaderColor: (color: string) => void
  setBackgroundColor: (color: string) => void
  showConfirm: (message: string, callback: (result: boolean) => void) => void
  HapticFeedback?: {
    impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
  }
  MainButton?: {
    setText: (text: string) => void
    show: () => void
    hide: () => void
    onClick: (callback: () => void) => void
    offClick: (callback: () => void) => void
    setParams: (params: { color: string; text_color: string }) => void
  }
}

type TelegramWindow = Window & {
  Telegram?: {
    WebApp?: TelegramWebAppLike
  }
}

export function useTelegram() {
  const tg = (window as TelegramWindow).Telegram?.WebApp;
  const isTMA = ref(!!tg && Object.keys(tg.initDataUnsafe || {}).length > 0);

  // 初始化 Telegram Web App
  onMounted(() => {
    if (isTMA.value && tg) {
      tg.ready();
      // 根据项目主题色设置 TMA 的 Header/Button 颜色
      try {
        tg.setHeaderColor('#0f172a'); // 比如使用 slate-900 作为 header
        tg.setBackgroundColor('#0f172a'); 
      } catch (e) {
        console.warn('Failed to set TMA colors:', e);
      }
    }
  });

  const hapticFeedback = (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft' = 'medium') => {
    if (isTMA.value && tg?.HapticFeedback) {
      tg.HapticFeedback.impactOccurred(style);
    }
  };

  const showMainButton = (text: string, onClick: () => void) => {
    if (isTMA.value && tg?.MainButton) {
      tg.MainButton.setText(text);
      tg.MainButton.show();
      tg.MainButton.onClick(onClick);
      // 可以配置统一的主题色
      tg.MainButton.setParams({
        color: '#0891b2', // cyan-600
        text_color: '#ffffff'
      });
    }
  };

  const hideMainButton = (onClick?: () => void) => {
    if (isTMA.value && tg?.MainButton) {
      tg.MainButton.hide();
      if (onClick) {
        tg.MainButton.offClick(onClick);
      }
    }
  };

  const showConfirm = (message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      if (isTMA.value && tg) {
        tg.showConfirm(message, (result: boolean) => {
          resolve(result);
        });
      } else {
        const result = window.confirm(message);
        resolve(result);
      }
    });
  };

  return {
    tg,
    isTMA,
    hapticFeedback,
    showMainButton,
    hideMainButton,
    showConfirm
  };
}
