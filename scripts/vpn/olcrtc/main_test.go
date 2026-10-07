package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

type localTransport struct {
	base http.RoundTripper
	url  string
}

func (t localTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	copy := r.Clone(r.Context())
	parsed := *r.URL
	target, _ := http.NewRequest("POST", t.url, nil)
	parsed.Host = target.URL.Host
	parsed.Scheme = target.URL.Scheme
	copy.URL = &parsed
	return t.base.RoundTrip(copy)
}
func TestAdmissionDeniesBeforeOpeningAndReleases(t *testing.T) {
	var mu sync.Mutex
	allowed := false
	actions := []string{}
	endpoint := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer private-token" {
			t.Error("missing authentication")
		}
		var body map[string]string
		_ = json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		actions = append(actions, body["action"])
		ok := allowed
		mu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]bool{"allowed": ok})
	}))
	defer endpoint.Close()
	a := &admission{cfg: roomConfig{AuthToken: "private-token"}, client: &http.Client{Transport: localTransport{http.DefaultTransport, endpoint.URL}}, sessions: map[string]session{}, cancel: func() {}}
	if _, err := a.auth("device", nil); err == nil {
		t.Fatal("inactive subscription accepted")
	}
	if len(a.sessions) != 0 {
		t.Fatal("denied session occupies a place")
	}
	mu.Lock()
	allowed = true
	mu.Unlock()
	sid, err := a.auth("device", nil)
	if err != nil {
		t.Fatal(err)
	}
	a.open(sid, "device", nil)
	a.close(sid, "left")
	if len(a.sessions) != 0 {
		t.Fatal("disconnected session retained")
	}
	mu.Lock()
	defer mu.Unlock()
	if actions[len(actions)-1] != "release" {
		t.Fatal("global place was not released")
	}
}
func TestHeartbeatCancelsWhenControlUnavailable(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	canceled := make(chan struct{}, 1)
	a := &admission{cfg: roomConfig{}, client: &http.Client{Transport: localTransport{http.DefaultTransport, "http://127.0.0.1:1"}, Timeout: time.Millisecond * 100}, sessions: map[string]session{"session": {device: "device", opened: true}}, cancel: func() { canceled <- struct{}{} }}
	go a.heartbeat(ctx)
	select {
	case <-canceled:
	case <-time.After(12 * time.Second):
		t.Fatal("lost control connection kept tunnel authorized")
	}
}
