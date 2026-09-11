package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

func signedTestConfig(t *testing.T, gatewayURL string) ([]byte, Config, string) {
	t.Helper()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader); if err != nil { t.Fatal(err) }
	cfg := Config{Version: 3, GatewayURL: gatewayURL, IdentityFingerprint: "edge-cert-sha256",
		PollSeconds: 5, Sources: []Source{{Name:"CNC-04",Protocol:"opcua",Address:"ns=2;s=State",
			AssetID:"asset-cnc-04",CanonicalSignal:"machine.state",Scale:1}}}
	raw, err := json.Marshal(cfg); if err != nil { t.Fatal(err) }
	payload, err := signedConfigPayload(raw); if err != nil { t.Fatal(err) }
	cfg.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey,payload))
	raw, err = json.Marshal(cfg); if err != nil { t.Fatal(err) }
	return raw,cfg,base64.StdEncoding.EncodeToString(publicKey)
}

func pendingCount(t *testing.T, db *sql.DB) int {
	t.Helper(); var count int; if err := db.QueryRow(`SELECT count(*) FROM pending_messages`).Scan(&count); err != nil { t.Fatal(err) }; return count
}

func TestConfigSignatureRejectsTampering(t *testing.T) {
	raw,cfg,publicKey := signedTestConfig(t,"https://example.invalid")
	if err := validateConfig(raw,cfg,publicKey); err != nil { t.Fatalf("valid signature rejected: %v",err) }
	var tampered map[string]any; if err := json.Unmarshal(raw,&tampered); err != nil { t.Fatal(err) }
	tampered["gateway_url"]="https://attacker.invalid"; changed, _ := json.Marshal(tampered)
	if err := validateConfig(changed,cfg,publicKey); err == nil { t.Fatal("tampered configuration was accepted") }
}

func TestStoreForwardSurvivesOutageRestartAndReplaysOnce(t *testing.T) {
	var unavailable atomic.Bool; unavailable.Store(true)
	var accepted atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
		if r.Header.Get("Idempotency-Key")!="edge-message-701" { t.Errorf("missing stable idempotency key") }
		if r.Header.Get("X-Edge-Identity")!="edge-cert-sha256" { t.Errorf("missing edge identity") }
		if unavailable.Load(){http.Error(w,"offline",http.StatusServiceUnavailable);return}
		var event CanonicalEvent; if err:=json.NewDecoder(r.Body).Decode(&event);err!=nil{t.Errorf("invalid event: %v",err)}
		if event.MessageID!="edge-message-701"{t.Errorf("unexpected event %s",event.MessageID)}
		accepted.Add(1); w.WriteHeader(http.StatusAccepted)
	})); defer server.Close()
	_,cfg,_:=signedTestConfig(t,server.URL)
	path:=filepath.Join(t.TempDir(),"edge.db")
	db,err:=openStore(path);if err!=nil{t.Fatal(err)}
	event:=CanonicalEvent{MessageID:"edge-message-701",EventType:"machine.alarm",AssetID:"asset-cnc-04",SourceTimestamp:time.Now().UTC(),Payload:map[string]any{"fault_code":"701"}}
	if err:=queue(db,event);err!=nil{t.Fatal(err)};if err:=queue(db,event);err!=nil{t.Fatal(err)}
	if pendingCount(t,db)!=1{t.Fatal("duplicate message was queued")}
	if err:=flush(context.Background(),db,cfg,server.Client());err!=nil{t.Fatal(err)}
	if pendingCount(t,db)!=1{t.Fatal("outage discarded durable event")}
	var attempts int;if err:=db.QueryRow(`SELECT attempts FROM pending_messages WHERE id=?`,event.MessageID).Scan(&attempts);err!=nil{t.Fatal(err)};if attempts!=1{t.Fatalf("attempts=%d",attempts)}
	if err:=db.Close();err!=nil{t.Fatal(err)}
	db,err=openStore(path);if err!=nil{t.Fatal(err)};defer db.Close()
	unavailable.Store(false)
	if err:=flush(context.Background(),db,cfg,server.Client());err!=nil{t.Fatal(err)}
	if pendingCount(t,db)!=0{t.Fatal("accepted replay remained queued")}
	if accepted.Load()!=1{t.Fatalf("accepted deliveries=%d",accepted.Load())}
}
