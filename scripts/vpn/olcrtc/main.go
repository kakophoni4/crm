// Build inside the pinned olcRTC module as cmd/crm-vpn; see build.py.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	appsession "github.com/openlibrecommunity/olcrtc/internal/app/session"
	"github.com/openlibrecommunity/olcrtc/internal/server"
	"github.com/openlibrecommunity/olcrtc/pkg/olcrtc/client"
)

type roomConfig struct {
	ID        string `json:"id"`
	Room      string `json:"room"`
	Key       string `json:"key"`
	AuthToken string `json:"auth_token"`
	Stats     string `json:"stats"`
	LocalAddr string `json:"local_addr,omitempty"`
	DeviceID  string `json:"device_id,omitempty"`
}
type session struct {
	device  string
	created time.Time
	opened  bool
}
type admission struct {
	cfg      roomConfig
	client   *http.Client
	mu       sync.Mutex
	sessions map[string]session
	cancel   context.CancelFunc
}

func (a *admission) lease(action, sid, device string) bool {
	body, _ := json.Marshal(map[string]string{"action": action, "subscription_id": a.cfg.ID, "lease_id": sid, "device_id": device})
	req, err := http.NewRequest(http.MethodPost, "http://127.0.0.1:9898/olcrtc", bytes.NewReader(body))
	if err != nil {
		return false
	}
	req.Header.Set("Authorization", "Bearer "+a.cfg.AuthToken)
	req.Header.Set("Content-Type", "application/json")
	response, err := a.client.Do(req)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	var result struct {
		Allowed bool `json:"allowed"`
	}
	return response.StatusCode == 200 && json.NewDecoder(response.Body).Decode(&result) == nil && result.Allowed
}
func (a *admission) auth(device string, _ map[string]any) (string, error) {
	if len(device) == 0 || len(device) > 256 {
		return "", errors.New("invalid device")
	}
	sid := uuid.NewString()
	if !a.lease("acquire", sid, device) {
		return "", errors.New("subscription unavailable or connection limit reached")
	}
	a.mu.Lock()
	a.sessions[sid] = session{device: device, created: time.Now()}
	a.mu.Unlock()
	return sid, nil
}
func (a *admission) open(sid, device string, _ map[string]any) {
	a.mu.Lock()
	if s, ok := a.sessions[sid]; ok {
		s.opened = true
		a.sessions[sid] = s
	}
	a.mu.Unlock()
}
func (a *admission) close(sid, _ string) {
	a.mu.Lock()
	s, ok := a.sessions[sid]
	delete(a.sessions, sid)
	a.mu.Unlock()
	if ok {
		a.lease("release", sid, s.device)
	}
}
func (a *admission) heartbeat(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()
	defer func() {
		a.mu.Lock()
		sessions := a.sessions
		a.sessions = map[string]session{}
		a.mu.Unlock()
		for sid, s := range sessions {
			a.lease("release", sid, s.device)
		}
	}()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
		a.mu.Lock()
		snapshot := make(map[string]session, len(a.sessions))
		for sid, s := range a.sessions {
			snapshot[sid] = s
		}
		a.mu.Unlock()
		for sid, s := range snapshot {
			if !s.opened && time.Since(s.created) > 20*time.Second {
				a.close(sid, "handshake timeout")
				continue
			}
			if !a.lease("renew", sid, s.device) {
				a.mu.Lock()
				_, stillOpen := a.sessions[sid]
				a.mu.Unlock()
				if stillOpen {
					a.cancel()
					return
				}
			}
		}
	}
}

type running struct {
	fingerprint string
	cancel      context.CancelFunc
	done        chan struct{}
}

func fingerprint(cfg roomConfig) string {
	value, _ := json.Marshal(cfg)
	sum := sha256.Sum256(value)
	return hex.EncodeToString(sum[:])
}
func valid(cfg roomConfig) bool {
	_, err := uuid.Parse(cfg.ID)
	key, ke := hex.DecodeString(cfg.Key)
	return err == nil && ke == nil && len(key) == 32 && len(cfg.Room) > 0 && len(cfg.AuthToken) == 64
}
func supervise(ctx context.Context, path string) {
	appsession.RegisterDefaults()
	active := map[string]running{}
	defer func() {
		for _, r := range active {
			r.cancel()
		}
	}()
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		data, err := os.ReadFile(path)
		var configs []roomConfig
		if err == nil && json.Unmarshal(data, &configs) == nil {
			desired := map[string]roomConfig{}
			for _, cfg := range configs {
				if valid(cfg) {
					desired[cfg.ID] = cfg
				}
			}
			for id, r := range active {
				cfg, exists := desired[id]
				finished := false
				select {
				case <-r.done:
					finished = true
				default:
				}
				if !exists || r.fingerprint != fingerprint(cfg) || finished {
					r.cancel()
					select {
					case <-r.done:
					case <-time.After(5 * time.Second):
					}
					delete(active, id)
				}
			}
			for id, cfg := range desired {
				if _, ok := active[id]; ok {
					continue
				}
				roomCtx, cancel := context.WithCancel(ctx)
				done := make(chan struct{})
				a := &admission{cfg: cfg, client: &http.Client{Timeout: 3 * time.Second}, sessions: map[string]session{}, cancel: cancel}
				active[id] = running{fingerprint(cfg), cancel, done}
				go a.heartbeat(roomCtx)
				go func(cfg roomConfig, a *admission) {
					defer close(done)
					defer cancel()
					_ = server.Run(roomCtx, server.Config{
						Provider: "jitsi", Transport: "datachannel", RoomURL: cfg.Room, KeyHex: cfg.Key,
						StatsListen: cfg.Stats, DNSServer: "1.1.1.1:53", AuthHook: a.auth, OnSessionOpen: a.open, OnSessionClose: a.close,
					})
				}(cfg, a)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	if len(os.Args) == 3 && os.Args[1] == "client" {
		var cfg roomConfig
		data, err := os.ReadFile(os.Args[2])
		if err != nil || json.Unmarshal(data, &cfg) != nil {
			os.Exit(2)
		}
		err = client.New(client.Config{Provider: "jitsi", Transport: "datachannel", RoomURL: cfg.Room, KeyHex: cfg.Key,
			LocalAddr: cfg.LocalAddr, DeviceID: cfg.DeviceID, DNSServer: "1.1.1.1:53"}).Run(ctx)
		if err != nil {
			os.Exit(1)
		}
		return
	}
	if len(os.Args) != 2 {
		os.Exit(2)
	}
	supervise(ctx, os.Args[1])
}
