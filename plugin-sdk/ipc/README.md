# Atlas Plugin IPC Protocol (M9b)

Newline-delimited JSON messages over stdin (host → plugin) and stdout (plugin → host).

## Host → Plugin

`host_ready` — sent once at startup:

```json
{"ipc_version":"1","type":"host_ready","plugin_id":"com.example.plugin","granted_capabilities":["read-config"],"mode":"normal","plugin_script":"/path/plugin.py"}
```

`capability_response` — response to a plugin request.

## Plugin → Host

`capability_request`:

```json
{"ipc_version":"1","type":"capability_request","request_id":"req-1","capability":"read-config","params":{}}
```

`shutdown` — plugin finished.

## Bootstrap

Launch via `python plugin-sdk/ipc/bootstrap.py <plugin_script> <mode>`. The bootstrap uses **stdlib only** and never imports Atlas backend code.

## Security

The plugin subprocess is isolated from Atlas memory/DB. Capability enforcement happens in the Atlas host when it receives `capability_request` messages.
