{{- define "multi-agent.fullname" -}}
{{ .Release.Name }}
{{- end -}}

{{- define "multi-agent.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "multi-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
component: backend
{{- end -}}
