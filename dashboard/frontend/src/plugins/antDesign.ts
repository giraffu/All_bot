import { defineAsyncComponent, type App, type Component } from 'vue'
import cssinjs from 'ant-design-vue/es/_util/cssinjs'
import Empty from 'ant-design-vue/es/empty'

type ModuleLoader = () => Promise<Record<string, unknown>>
type ComponentResolver = (module: Record<string, unknown>) => Component

const defaultExport = (module: Record<string, unknown>) => module.default as Component
const namedExport =
  (name: string): ComponentResolver =>
  (module) =>
    module[name] as Component

const registerAsyncComponent = (
  app: App,
  name: string,
  loader: ModuleLoader,
  resolveComponent: ComponentResolver = defaultExport
) => {
  app.component(
    name,
    defineAsyncComponent({
      loader: () => loader().then(resolveComponent),
      suspensible: false,
    })
  )
}

export function installAntDesign(app: App) {
  app.use(cssinjs.StyleProvider)

  registerAsyncComponent(app, 'a-alert', () => import('ant-design-vue/es/alert'))
  registerAsyncComponent(app, 'a-avatar', () => import('ant-design-vue/es/avatar'))
  registerAsyncComponent(app, 'a-badge', () => import('ant-design-vue/es/badge'))
  registerAsyncComponent(app, 'a-breadcrumb', () => import('ant-design-vue/es/breadcrumb'))
  registerAsyncComponent(
    app,
    'a-breadcrumb-item',
    () => import('ant-design-vue/es/breadcrumb'),
    namedExport('BreadcrumbItem')
  )
  registerAsyncComponent(app, 'a-button', () => import('ant-design-vue/es/button'))
  registerAsyncComponent(app, 'a-card', () => import('ant-design-vue/es/card'))
  registerAsyncComponent(app, 'a-checkbox', () => import('ant-design-vue/es/checkbox'))
  registerAsyncComponent(app, 'a-col', () => import('ant-design-vue/es/col'))
  registerAsyncComponent(app, 'a-date-picker', () => import('ant-design-vue/es/date-picker'))
  registerAsyncComponent(app, 'a-range-picker', () => import('ant-design-vue/es/date-picker'), (module) => {
    const datePicker = defaultExport(module) as Component & { RangePicker?: Component }
    return datePicker.RangePicker as Component
  })
  registerAsyncComponent(app, 'a-divider', () => import('ant-design-vue/es/divider'))
  registerAsyncComponent(app, 'a-dropdown', () => import('ant-design-vue/es/dropdown'))
  app.component('a-empty', Empty)
  registerAsyncComponent(app, 'a-form', () => import('ant-design-vue/es/form'))
  registerAsyncComponent(
    app,
    'a-form-item',
    () => import('ant-design-vue/es/form'),
    namedExport('FormItem')
  )
  registerAsyncComponent(app, 'a-image', () => import('ant-design-vue/es/image'))
  registerAsyncComponent(app, 'a-input', () => import('ant-design-vue/es/input'))
  registerAsyncComponent(app, 'a-input-password', () => import('ant-design-vue/es/input'), (module) => {
    const input = defaultExport(module) as Component & { Password?: Component }
    return input.Password as Component
  })
  registerAsyncComponent(app, 'a-input-search', () => import('ant-design-vue/es/input'), (module) => {
    const input = defaultExport(module) as Component & { Search?: Component }
    return input.Search as Component
  })
  registerAsyncComponent(app, 'a-textarea', () => import('ant-design-vue/es/input'), (module) => {
    const input = defaultExport(module) as Component & { TextArea?: Component }
    return input.TextArea as Component
  })
  registerAsyncComponent(app, 'a-input-number', () => import('ant-design-vue/es/input-number'))
  registerAsyncComponent(app, 'a-layout', () => import('ant-design-vue/es/layout'))
  registerAsyncComponent(
    app,
    'a-layout-content',
    () => import('ant-design-vue/es/layout'),
    namedExport('LayoutContent')
  )
  registerAsyncComponent(
    app,
    'a-layout-header',
    () => import('ant-design-vue/es/layout'),
    namedExport('LayoutHeader')
  )
  registerAsyncComponent(
    app,
    'a-layout-sider',
    () => import('ant-design-vue/es/layout'),
    namedExport('LayoutSider')
  )
  registerAsyncComponent(app, 'a-menu', () => import('ant-design-vue/es/menu'))
  registerAsyncComponent(app, 'a-menu-item', () => import('ant-design-vue/es/menu'), namedExport('MenuItem'))
  registerAsyncComponent(app, 'a-modal', () => import('ant-design-vue/es/modal'))
  registerAsyncComponent(app, 'a-pagination', () => import('ant-design-vue/es/pagination'))
  registerAsyncComponent(app, 'a-popconfirm', () => import('ant-design-vue/es/popconfirm'))
  registerAsyncComponent(app, 'a-progress', () => import('ant-design-vue/es/progress'))
  registerAsyncComponent(app, 'a-radio-group', () => import('ant-design-vue/es/radio'), namedExport('Group'))
  registerAsyncComponent(app, 'a-radio-button', () => import('ant-design-vue/es/radio'), namedExport('Button'))
  registerAsyncComponent(app, 'a-row', () => import('ant-design-vue/es/row'))
  registerAsyncComponent(app, 'a-select', () => import('ant-design-vue/es/select'))
  registerAsyncComponent(app, 'a-select-option', () => import('ant-design-vue/es/select'), namedExport('Option'))
  registerAsyncComponent(app, 'a-spin', () => import('ant-design-vue/es/spin'))
  registerAsyncComponent(app, 'a-statistic', () => import('ant-design-vue/es/statistic'))
  registerAsyncComponent(app, 'a-switch', () => import('ant-design-vue/es/switch'))
  registerAsyncComponent(app, 'a-table', () => import('ant-design-vue/es/table'))
  registerAsyncComponent(app, 'a-table-column', () => import('ant-design-vue/es/table'), namedExport('TableColumn'))
  registerAsyncComponent(app, 'a-tabs', () => import('ant-design-vue/es/tabs'))
  registerAsyncComponent(app, 'a-tab-pane', () => import('ant-design-vue/es/tabs'), namedExport('TabPane'))
  registerAsyncComponent(app, 'a-tag', () => import('ant-design-vue/es/tag'))
  registerAsyncComponent(app, 'a-tooltip', () => import('ant-design-vue/es/tooltip'))
}
