package main

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "modernc.org/sqlite"
)

type Config struct {
	Version int `json:"version"`
	Signature string `json:"signature"`
	GatewayURL string `json:"gateway_url"`
	IdentityFingerprint string `json:"identity_fingerprint"`
	PollSeconds int `json:"poll_seconds"`
	Sources []Source `json:"sources"`
}

type Source struct {
	Name string `json:"name"`; Protocol string `json:"protocol"`; Address string `json:"address"`
	AssetID string `json:"asset_id"`; CanonicalSignal string `json:"canonical_signal"`
	SourceUnit string `json:"source_unit,omitempty"`; CanonicalUnit string `json:"canonical_unit,omitempty"`
	Scale float64 `json:"scale"`
}
type CanonicalEvent struct { MessageID string `json:"message_id"`; EventType string `json:"event_type"`; AssetID string `json:"asset_id"`; SourceTimestamp time.Time `json:"source_timestamp"`; Payload map[string]any `json:"payload"` }

func openStore(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil { return nil, err }
	for _, ddl := range []string{
		`CREATE TABLE IF NOT EXISTS pending_messages (id TEXT PRIMARY KEY, payload BLOB NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS configuration_versions (version INTEGER PRIMARY KEY, signature TEXT NOT NULL, payload BLOB NOT NULL, activated_at TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS source_health (source_name TEXT PRIMARY KEY, status TEXT NOT NULL, message TEXT, observed_at TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS command_log (id TEXT PRIMARY KEY, operation TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL)`,
	} { if _, err = db.Exec(ddl); err != nil { return nil, err } }
	return db, nil
}

func signedConfigPayload(raw []byte) ([]byte, error) {
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil { return nil, err }
	delete(payload, "signature")
	return json.Marshal(payload)
}

func validateConfig(raw []byte, cfg Config, signingPublicKey string) error {
	if cfg.Version < 1 || cfg.Signature == "" || cfg.IdentityFingerprint == "" { return errors.New("signed versioned configuration and certificate identity are required") }
	publicKey, err := base64.StdEncoding.DecodeString(signingPublicKey); if err != nil || len(publicKey) != ed25519.PublicKeySize { return errors.New("valid Ed25519 config signing public key is required") }
	signature, err := base64.StdEncoding.DecodeString(cfg.Signature); if err != nil || len(signature) != ed25519.SignatureSize { return errors.New("configuration signature is not valid base64 Ed25519 evidence") }
	signed, err := signedConfigPayload(raw); if err != nil { return err }
	if !ed25519.Verify(ed25519.PublicKey(publicKey), signed, signature) { return errors.New("configuration signature verification failed") }
	if len(cfg.Sources) == 0 { return errors.New("at least one allowlisted source mapping is required") }
	for _, source := range cfg.Sources {
		if source.AssetID == "" || source.CanonicalSignal == "" { return errors.New("every source must map to a canonical asset signal") }
		if source.Protocol != "opcua" && source.Protocol != "mqtt" { return fmt.Errorf("protocol %q is not allowlisted", source.Protocol) }
	}
	return nil
}

func queue(db *sql.DB, event CanonicalEvent) error { raw, _ := json.Marshal(event); _, err := db.Exec(`INSERT OR IGNORE INTO pending_messages(id,payload,created_at) VALUES(?,?,?)`, event.MessageID, raw, time.Now().UTC().Format(time.RFC3339Nano)); return err }

func flush(ctx context.Context, db *sql.DB, cfg Config, client *http.Client) error {
	type pending struct { id string; raw []byte }
	rows, err := db.QueryContext(ctx, `SELECT id,payload FROM pending_messages ORDER BY created_at LIMIT 100`); if err != nil { return err }
	batch := make([]pending,0,100)
	for rows.Next() { var item pending; if err := rows.Scan(&item.id,&item.raw); err != nil { _ = rows.Close(); return err }; batch=append(batch,item) }
	if err := rows.Err(); err != nil { _ = rows.Close(); return err }; if err := rows.Close(); err != nil { return err }
	for _, item := range batch { id, raw := item.id, item.raw
		req, _ := http.NewRequestWithContext(ctx, http.MethodPost, cfg.GatewayURL+"/api/v2/edge/events", bytes.NewReader(raw)); req.Header.Set("Content-Type","application/json"); req.Header.Set("X-Edge-Identity",cfg.IdentityFingerprint); req.Header.Set("X-Config-Signature",cfg.Signature); req.Header.Set("Idempotency-Key",id)
		resp, err := client.Do(req); if err != nil { _, _ = db.Exec(`UPDATE pending_messages SET attempts=attempts+1 WHERE id=?`,id); continue }; _ = resp.Body.Close()
		if resp.StatusCode >= 200 && resp.StatusCode < 300 { _, _ = db.Exec(`DELETE FROM pending_messages WHERE id=?`,id) } else { _, _ = db.Exec(`UPDATE pending_messages SET attempts=attempts+1 WHERE id=?`,id) }
	}; return nil
}

func main() {
	configPath := os.Getenv("GG_EDGE_CONFIG"); if configPath == "" { configPath = "config.json" }; dbPath := os.Getenv("GG_EDGE_DB"); if dbPath == "" { dbPath = "edge.db" }
	raw, err := os.ReadFile(configPath); if err != nil { log.Fatal(err) }; var cfg Config; if err = json.Unmarshal(raw,&cfg); err != nil { log.Fatal(err) }; if err = validateConfig(raw,cfg,os.Getenv("GG_EDGE_SIGNING_PUBLIC_KEY")); err != nil { log.Fatal(err) }
	db, err := openStore(dbPath); if err != nil { log.Fatal(err) }; defer db.Close(); _, _ = db.Exec(`INSERT OR REPLACE INTO configuration_versions VALUES(?,?,?,?)`,cfg.Version,cfg.Signature,raw,time.Now().UTC().Format(time.RFC3339Nano))
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM); defer stop(); client := &http.Client{Timeout:10*time.Second}; ticker := time.NewTicker(time.Duration(max(cfg.PollSeconds,5))*time.Second); defer ticker.Stop()
	log.Printf("edge runtime %d active; outbound transport only; %d source mappings",cfg.Version,len(cfg.Sources))
	for { select { case <-ctx.Done(): return; case now := <-ticker.C: for _, source := range cfg.Sources { sum := sha256.Sum256([]byte(source.Name+now.UTC().Format(time.RFC3339Nano))); _ = queue(db,CanonicalEvent{MessageID:hex.EncodeToString(sum[:]),EventType:source.CanonicalSignal,AssetID:source.AssetID,SourceTimestamp:now.UTC(),Payload:map[string]any{"source":source.Name,"simulation":true}}); _, _ = db.Exec(`INSERT OR REPLACE INTO source_health VALUES(?,?,?,?)`,source.Name,"healthy","representative adapter heartbeat",now.UTC().Format(time.RFC3339Nano)) }; _ = flush(ctx,db,cfg,client) } }
}
