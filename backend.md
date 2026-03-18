# 后端系统技术报告

## 1. API 接口文档

本系统基于 RESTful 风格设计，采用 OpenAPI 3.0 标准。所有接口均通过 HTTP/HTTPS 协议访问。

### 1.1 通用说明

- **基础路径**: `/`
- **认证方式**: Bearer Token (Header: `Authorization: Bearer <token>`)
- **数据格式**: 请求体支持 `multipart/form-data` (用于文件上传) 和 `application/json`。响应体默认为 `application/json`。

### 1.2 核心接口详解

#### 1.2.1 图生图任务 (Image to Image)

- **路径**: `/comfy_img2img`
- **方法**: `POST`
- **描述**: 上传一张参考图和提示词，生成新的图像。
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 参考图像文件。
  - `prompt` (String, 必填): 生成提示词。
  - `priority` (Integer, 选填): 任务优先级，默认 0 (高优先级数字越大? 代码逻辑为 `-(priority * 10^10) + timestamp`，因此数字越大优先级越高)。
- **响应示例**:
  ```json
  {
    "task_id": "d633584f-10ac-4683-86e4-8a044f3cb2f8"
  }
  ```

#### 1.2.2 人脸替换任务 (Face Swap)

- **路径**: `/face_swap`
- **方法**: `POST`
- **描述**: 将源人脸替换到目标身体图像上。
- **请求参数 (multipart/form-data)**:
  - `face_image` (File, 必填): 提供人脸的源图像。
  - `body_image` (File, 必填): 提供身体的目标图像。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**:
  ```json
  {
    "task_id": "9107570e-cf35-4d42-8ea2-9c4070e9811b"
  }
  ```

#### 1.2.3 视频植入任务 (Video Insert)

- **路径**: `/perfect_video_insert`
- **方法**: `POST`
- **描述**: 将图像植入到视频生成流程中。
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 输入图像。
  - `prompt` (String, 必填): 提示词。
  - `width` (Integer, 默认 512): 视频宽度。
  - `height` (Integer, 默认 512): 视频高度。
  - `length` (Integer, 默认 81): 视频帧数/长度。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**: 同上。

#### 1.2.4 视频编辑任务 (Video Edit)

- **路径**: `/perfect_video_edit`
- **方法**: `POST`
- **描述**: 基于图像和提示词编辑生成视频。
- **请求参数**: 同 "视频植入任务"。
- **响应示例**: 同上。

#### 1.2.5 文生图 Turbo 任务 (T2I Pornmaster Turbo)

- **路径**: `/api/v1/workflows/t2i-pornmaster-turbo`
- **方法**: `POST`
- **描述**: 文生图工作流，集成 Double checkpoints 与现实增强器。
- **请求参数 (application/json)**:
  - `prompt` (String, 必填): 生成提示词，长度 1-512。
- **查询参数**:
  - `async` (Boolean, 默认 true): 是否异步执行。若为 `false`，则同步阻塞等待结果（超时 60s）。
- **响应示例**:
  ```json
  {
    "task_id": "893c8340-96f3-469a-9e22-861f60049f57",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```
- **cURL 示例**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/workflows/t2i-pornmaster-turbo?async=false" \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"prompt": "一張來自日本90年代Tokyo-Hot色情片中的一位可愛18歲日本女性照片"}'
  ```
- **前端调用示例 (JavaScript)**:
  ```javascript
  const response = await fetch('/api/v1/workflows/t2i-pornmaster-turbo', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ prompt: 'your prompt here' })
  });
  const data = await response.json();
  console.log('Task ID:', data.task_id);
  ```

#### 1.2.6 查询任务状态 (V1)

- **路径**: `/api/v1/tasks/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务详情，包括生成图片的 URL。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "progress": 1.0,
    "result_path": "comfyui_00001_.png",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```

#### 1.2.7 查询任务状态 (Legacy)

- **路径**: `/status/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务的当前状态、队列位置及进度。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "queue_remaining": 0,
    "progress": 1.0,
    "error": null,
    "result_path": "ComfyUI_00001_.png"
  }
  ```
- **状态码定义**:
  - `pending`: 排队中
  - `running`: 执行中
  - `done`: 已完成
  - `error`: 失败

#### 1.2.6 获取结果文件

- **路径**: `/image/{task_id}` 或 `/video/{task_id}`
- **方法**: `GET`
- **描述**: 下载任务生成的图片或视频文件。
- **错误处理**:
  - `404 Not Found`: 文件不存在或任务未完成。

#### 1.2.7 系统状态

- **路径**: `/system/status`
- **方法**: `GET`
- **响应示例**:
  ```json
  {
    "queue_size": 5,
    "active_workers": 1,
    "comfy_online": true
  }
  ```

***
