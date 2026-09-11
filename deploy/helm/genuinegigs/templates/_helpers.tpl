{{- define "genuinegigs.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "genuinegigs.secretEnv" -}}
- name: DATABASE_URL
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.databaseUrlKey }}}}
- name: REDIS_URL
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.redisUrlKey }}}}
- name: SESSION_SECRET
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.sessionSecretKey }}}}
- name: GROQ_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.groqApiKeyKey }}, optional: true}}
- name: LLAMA_CLOUD_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.llamaCloudApiKeyKey }}, optional: true}}
- name: GEMINI_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.geminiApiKeyKey }}, optional: true}}
- name: OBJECT_STORAGE_ENDPOINT
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.objectStorageEndpointKey }}}}
- name: OBJECT_STORAGE_ACCESS_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.objectStorageAccessKeyKey }}}}
- name: OBJECT_STORAGE_SECRET_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretRef.name }}, key: {{ .Values.secretRef.objectStorageSecretKeyKey }}}}
{{- end -}}

{{- define "genuinegigs.labels" -}}
app.kubernetes.io/name: {{ include "genuinegigs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
