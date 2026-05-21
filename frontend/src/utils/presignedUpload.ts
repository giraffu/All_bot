import api from '@/api'

export interface PresignedUploadPayload {
  upload_url: string
  object_key: string
}

export interface PresignedUploadRequestOptions {
  signal?: AbortSignal
}

export interface DirectUploadOptions {
  xhr?: XMLHttpRequest
  beforeSend?: () => boolean | void
  onProgress?: (event: ProgressEvent<XMLHttpRequestEventTarget>) => void
  onAbort?: () => void
}

export async function requestPresignedUpload(
  file: File,
  options: PresignedUploadRequestOptions = {}
): Promise<PresignedUploadPayload> {
  const { data } = await api.get('/storage/presigned-url', {
    params: {
      filename: file.name,
      content_type: file.type || 'application/octet-stream'
    },
    signal: options.signal
  })
  return data
}

export function uploadFileToPresignedUrl(
  file: File,
  payload: PresignedUploadPayload,
  options: DirectUploadOptions = {}
): Promise<string | null> {
  const xhr = options.xhr ?? new XMLHttpRequest()

  return new Promise((resolve, reject) => {
    if (options.beforeSend?.() === false) {
      resolve(null)
      return
    }

    xhr.open('PUT', payload.upload_url, true)

    xhr.upload.onprogress = (event) => {
      options.onProgress?.(event)
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload.object_key)
        return
      }
      reject(new Error(`Upload failed with status ${xhr.status}`))
    }

    xhr.onabort = () => {
      options.onAbort?.()
      resolve(null)
    }

    xhr.onerror = () => {
      reject(new Error('Network error during upload'))
    }

    // Strip MIME type to avoid implicit Content-Type on signed upload requests.
    const blobToUpload = new Blob([file], { type: '' })
    xhr.send(blobToUpload)
  })
}
