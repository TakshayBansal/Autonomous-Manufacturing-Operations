# GenuineGigs edge agent

Plant-network runtime for read-only OPC UA/MQTT source normalization and durable outbound delivery. It keeps `pending_messages`, `configuration_versions`, `source_health`, and `command_log` in local SQLite. It exposes no inbound listener and has no PLC write implementation.

Configuration must be provisioned as a signed, versioned file with a per-edge certificate fingerprint. `GG_EDGE_SIGNING_PUBLIC_KEY` must contain the trusted Ed25519 public key in base64; it is provisioned separately from the config so replacing the file cannot replace its trust root. The signature is computed over canonical compact JSON after removing the top-level `signature` field. Startup fails closed for a missing key, malformed signature, changed endpoint, or changed source mapping.

Every queued event uses its stable message ID as the HTTP `Idempotency-Key`. Non-2xx responses and network failures increment the durable attempt count without removing the message. A later process restart reopens the same SQLite file and replays in creation order; only a 2xx acknowledgement removes an event.

The current adapters emit representative canonical heartbeats; customer-specific OPC UA/MQTT clients plug into the same allowlisted `Source` mappings without changing the platform event contract. The runtime exposes no inbound listener and contains no PLC-write capability.

Run `go test ./...` to exercise signed-config tamper rejection and outage → process restart → replay with duplicate queue suppression. Those tests require Go 1.23; they cannot execute on hosts without a Go toolchain.
