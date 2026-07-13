import {
  computed,
  inject,
  onBeforeUnmount,
  watch,
  type ComputedRef,
  type InjectionKey,
  type Ref
} from 'vue'

export type MainLayoutContentRef = ComputedRef<HTMLElement | null> | Ref<HTMLElement | null>

export const mainLayoutContentRefKey: InjectionKey<MainLayoutContentRef> =
  Symbol('mainLayoutContentRef')

export function useMainLayoutContentRef(): ComputedRef<HTMLElement | null> {
  const injectedContentRef = inject(mainLayoutContentRefKey, null)
  return computed(() => injectedContentRef?.value ?? null)
}

export function useWorkbenchScrollLock(
  contentRef: MainLayoutContentRef,
  activeRef: ComputedRef<boolean> | Ref<boolean>
) {
  let previousOverflow = ''
  let previousScrollTop = 0
  let lockedElement: HTMLElement | null = null

  const lock = (element: HTMLElement) => {
    if (lockedElement === element) {
      return
    }

    previousOverflow = element.style.overflow
    previousScrollTop = element.scrollTop
    element.style.overflow = 'hidden'
    lockedElement = element
  }

  const unlock = () => {
    if (!lockedElement) {
      return
    }

    lockedElement.style.overflow = previousOverflow
    lockedElement.scrollTop = previousScrollTop
    lockedElement = null
  }

  watch(
    () => activeRef.value,
    (active) => {
      const element = contentRef.value
      if (!element) {
        return
      }

      if (active) {
        lock(element)
        return
      }

      unlock()
    },
    { immediate: true }
  )

  onBeforeUnmount(() => {
    unlock()
  })
}
