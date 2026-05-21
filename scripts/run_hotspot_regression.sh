#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
用法:
  ./scripts/run_hotspot_regression.sh <group> [group...]

可用分组:
  task-facade     task_service facade/support focused 回归
  task-min        任务黄金路径最小必跑集
  task-full       任务黄金路径完整回归
  tasks-web       tasks Web API 回归
  users-web       users Web API 回归
  gallery-web     gallery Web API 回归
  message-handler Telegram message_handler 回归
  frontend-shared 前端公共壳层 / 模板应用 / 列表态回归
  help            显示帮助

示例:
  ./scripts/run_hotspot_regression.sh task-full
  ./scripts/run_hotspot_regression.sh gallery-web frontend-shared
EOF
}

run_pytest_group() {
  local label="$1"
  shift
  echo ""
  echo "==> Running ${label}"
  (cd "${ROOT_DIR}" && pytest "$@")
}

run_frontend_vitest_group() {
  local label="$1"
  shift
  echo ""
  echo "==> Running ${label}"
  (
    cd "${ROOT_DIR}/frontend"
    if command -v pnpm >/dev/null 2>&1; then
      pnpm vitest run "$@"
    else
      npm exec -- vitest run "$@"
    fi
  )
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

for group in "$@"; do
  case "${group}" in
    help|-h|--help)
      usage
      exit 0
      ;;
    task-facade)
      run_pytest_group "task-facade" \
        tests/services/test_task_service_flow.py \
        tests/services/test_task_service_completion.py \
        tests/services/test_task_service_support.py \
        tests/services/test_task_service_message_support.py \
        tests/services/test_task_service_entrypoint_support.py \
        src/tests/test_task_service_refactored.py \
        src/tests/test_queue_logic.py
      ;;
    task-min)
      run_pytest_group "task-min" \
        tests/backend/test_main_helpers.py \
        tests/backend/test_queue_manager.py \
        tests/web_api/test_tasks_action_api_service.py \
        tests/web_api/test_tasks_router_passthrough.py \
        tests/web_api/test_tasks_stream.py \
        tests/services/test_task_service_completion.py \
        tests/services/test_task_service_support.py \
        tests/services/test_task_service_message_support.py \
        tests/services/test_task_service_entrypoint_support.py \
        src/tests/test_task_service_refactored.py \
        src/tests/test_queue_logic.py
      ;;
    task-full)
      run_pytest_group "task-full" \
        tests/integration/test_saga_and_queue.py \
        tests/backend/test_main_helpers.py \
        tests/backend/test_queue_manager.py \
        tests/web_api/test_tasks_action_api_service.py \
        tests/web_api/test_tasks_router_passthrough.py \
        tests/web_api/test_tasks_stream.py \
        tests/services/test_task_service_completion.py \
        tests/services/test_task_service_flow.py \
        tests/services/test_task_service_support.py \
        tests/services/test_task_service_message_support.py \
        tests/services/test_task_service_entrypoint_support.py \
        src/tests/test_task_service_refactored.py \
        src/tests/test_queue_logic.py
      ;;
    tasks-web)
      run_pytest_group "tasks-web" \
        tests/web_api/test_tasks_action_api_service.py \
        tests/web_api/test_tasks_router_passthrough.py \
        tests/web_api/test_tasks_stream.py
      ;;
    users-web)
      run_pytest_group "users-web" \
        tests/web_api/test_users_apply_context.py \
        tests/web_api/test_users_history_urls.py \
        tests/web_api/test_users_history_mutation_service.py \
        tests/web_api/test_users_affiliate_redeem.py \
        tests/web_api/test_users_affiliate_redeem_router.py
      ;;
    gallery-web)
      run_pytest_group "gallery-web" \
        tests/web_api/test_gallery_router_passthrough.py \
        tests/web_api/test_gallery_apply_context.py \
        tests/web_api/test_gallery_media_urls.py \
        tests/web_api/test_gallery_comments.py \
        tests/web_api/test_gallery_post_deletion.py \
        tests/web_api/test_gallery_task_type_filters.py
      ;;
    message-handler)
      run_pytest_group "message-handler" \
        tests/handlers/test_message_handler.py \
        tests/handlers/test_message_handler_common.py \
        tests/handlers/test_message_handler_profile.py \
        tests/handlers/test_message_handler_media.py \
        tests/handlers/test_message_handler_menu.py
      ;;
    frontend-shared)
      run_frontend_vitest_group "frontend-shared" \
        src/views/Gallery.test.ts \
        src/views/GalleryWorkbenchFlow.test.ts \
        src/views/MyFavoritesFlow.test.ts \
        src/components/MySubmissionsPanelFlow.test.ts \
        src/components/ListStateBlock.test.ts \
        src/components/template-apply/TemplateApplyWorkbenchHost.test.ts \
        src/router/index.test.ts \
        src/stores/tasksRuntime.test.ts \
        src/stores/taskResultState.test.ts \
        src/stores/templateApply.test.ts \
        src/composables/useTemplateApplyUpload.test.ts \
        src/utils/normalizeTemplateApplyContext.test.ts
      ;;
    *)
      echo "未知分组: ${group}" >&2
      usage
      exit 1
      ;;
  esac
done
