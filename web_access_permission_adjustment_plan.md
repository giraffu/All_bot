# 权限调整方案：将 Web 端访问门槛下调至“练气期”

## 1. 方案背景
目前系统针对 Web 端的访问门槛设定为：身份必须达到“内门弟子”及以上，**或** 修为境界必须达到“金丹期”及以上。
本方案旨在将修为境界的最低准入门槛由“金丹期”下调为“练气期”（包含练气期、筑基期、金丹期及以上境界），以扩大 Web 端的内测或开放范围，同时保持既有的付费身份（内门弟子及以上）门槛不变。

## 2. 影响范围分析
由于项目采用了双轨制（Bot + Web）且前后端分离，权限判定逻辑分布在以下几个核心节点：
1. **全局常量定义**：后端核心配置文件。
2. **后端 API 拦截与报错文案**：FastAPI 依赖注入拦截，以及登录、绑定等核心业务的报错提示语。
3. **Bot 菜单渲染**：控制“个人中心”下方“Web端 / Mini App”入口按钮的显示与隐藏。
4. **前端路由守卫**：Vue Router 拦截器，防止 URL 直接访问。
5. **前端登录逻辑**：登录页对 Telegram 授权登录、Mini App 自动登录等场景的数据二次校验及 UI 错误提示。
6. **文档与客服话术**：业务文档及 AI 客服的系统提示词。

---

## 3. 具体实施步骤与代码修改点

### 3.1 后端核心常量与权限判断调整
后端通过维护硬编码常量来判断权限，需增加 `练气期` 和 `筑基期`，并同步修改相关的报错提示文案。

* **文件 1**：`src/constants.py`
  * **目标变量**：`WEB_ACCESS_ALLOWED_GROUPS`
  * **修改方案**：在数组开头补充 `"练气期"` 和 `"筑基期"`。
  * **预期代码**：
    ```python
    WEB_ACCESS_ALLOWED_GROUPS = ["练气期", "筑基期", "金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期"]
    ```

* **文件 2**：`src/web_api/dependencies.py`
  * **目标逻辑**：`get_current_user` 函数中的硬编码权限校验列表。
  * **修改方案**：将此处的硬编码替换为统一引用 `constants.py` 中的 `WEB_ACCESS_ALLOWED_GROUPS` 和 `WEB_ACCESS_ALLOWED_IDENTITIES`。

* **文件 3**：`src/core/auth_core.py`
  * **目标逻辑**：`authenticate_user_by_password` 和 `bind_user_password` 函数中的报错提示语。
  * **修改方案**：将抛出异常的提示语由“只有金丹期...”改为“权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录/绑定 Web 端”。

* **文件 4**：`src/web_api/routers/auth.py`
  * **目标逻辑**：`login_telegram` 接口中的报错提示。
  * **修改方案**：同步将 `detail` 提示文案中的“金丹期”修改为“练气期”。

### 3.2 Bot 端入口按钮渲染逻辑调整
控制 Telegram Bot 中“个人中心”菜单下方“合欢密宗”入口按钮是否显示的门面服务。

* **文件 5**：`src/core/user_facade.py`
  * **目标变量**：`get_user_dashboard_info` 函数内部的 `allowed_groups` 和 `allowed_identities` 变量。
  * **修改方案**：重构为统一引用 `constants.py`，避免多处硬编码。

### 3.3 前端页面与路由拦截器调整
前端维护了对应的权限数组及相关的中文错误提示，需要覆盖所有登录场景。

* **文件 6**：`frontend/src/router/index.ts`
  * **目标逻辑**：`router.beforeEach` 路由守卫中的 `allowedGroups` 数组及权限不足提示语。
  * **修改方案**：在 `allowedGroups` 数组中增加 `'练气期', '筑基期'`，并修改拦截提示文本 `message.error`。

* **文件 7**：`frontend/src/views/Login.vue`
  * **目标逻辑**：处理 TG 授权登录成功后的回调 `handleTelegramAuth` 以及处理 Mini App 自动登录的 `checkWebAppLogin` 函数。
  * **修改方案**：
    1. 在这两个函数内部的 `allowedGroups` 数组中均增加 `'练气期', '筑基期'`。
    2. 确保采用 `message.error(...)` 组件替换相应的“金丹期”文本，改为“练气期”。

---

## 4. 实施风险与注意事项
1. **测试边界**：修改后，需准备一个刚注册的“凡人”账号，确认其依然**无法**登录 Web 端，并且在 Bot 个人中心看不到 Web 端入口。
2. **硬编码重构建议（强烈推荐）**：
   * **后端重构**：不仅要将 `WEB_ACCESS_ALLOWED_GROUPS`，也应将 `WEB_ACCESS_ALLOWED_IDENTITIES` 一并引入到 `dependencies.py` 和 `user_facade.py` 中，彻底解耦权限判断。
   * **前端重构**：前端多处重复编写了 `allowedGroups.includes(...)` 的判断逻辑。最佳实践是在 `frontend/src/stores/auth.ts` 中新增一个 `hasWebAccess` 的 getter 属性集中管理常量与判断。后续路由守卫和登录页只需调用 `authStore.hasWebAccess` 即可，极大降低未来维护成本。