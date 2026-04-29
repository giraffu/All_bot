import { useMediaQuery } from '@vueuse/core';

export function useViewport() {
  // 768px as the breakpoint for mobile
  const isMobile = useMediaQuery('(max-width: 767px)');
  
  return {
    isMobile,
  };
}
