import { hydrateRuntimeEntryVisibility } from './config/runtimeEntryVisibility'

const bootstrap = async () => {
  await hydrateRuntimeEntryVisibility()
  const { mountApp } = await import('./mountApp')
  mountApp()
}

void bootstrap()
