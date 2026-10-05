package dispatcher

// CRM admission is opt-in, loopback-only, and applies solely to CRM-managed users.
// One admission is shared by all streams from a user/IP on this node.
import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	stdnet "net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/xtls/xray-core/common/session"
)

type crmGuard struct {
	lease   string
	ready   chan struct{}
	allowed bool
	refs    map[*crmGuardRef]bool
}

var crmGuardEnabled = func() bool { _, err := os.Stat("/etc/crm-vpn/xray-guard.enabled"); return err == nil }()
var crmGuardMu sync.Mutex
var crmGuards = map[string]*crmGuard{}
var crmGuardHTTP = &http.Client{Timeout: 7 * time.Second, Transport: &http.Transport{Proxy: nil, MaxIdleConnsPerHost: 16}}
var crmGuardURL = "http://127.0.0.1:9898/guard"

func crmGuardRequest(action, lease, identity, ip string) bool {
	body, _ := json.Marshal(map[string]string{"action": action, "lease_id": lease, "subscription_id": identity, "ip": ip})
	resp, err := crmGuardHTTP.Post(crmGuardURL, "application/json", bytes.NewReader(body))
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	var result struct {
		Allowed bool `json:"allowed"`
	}
	return resp.StatusCode == 200 && json.NewDecoder(resp.Body).Decode(&result) == nil && result.Allowed
}

func crmGuardContext(ctx context.Context) (context.Context, error) {
	inbound := session.InboundFromContext(ctx)
	if !crmGuardEnabled || inbound == nil || inbound.User == nil || !strings.HasPrefix(inbound.User.Email, "crm-vpn-") {
		return ctx, nil
	}
	identity := strings.TrimPrefix(inbound.User.Email, "crm-vpn-")
	ip := inbound.Source.Address.String()
	parsed := stdnet.ParseIP(ip)
	if len(identity) != 36 || parsed == nil {
		return ctx, fmt.Errorf("invalid CRM source")
	}
	ip = parsed.String()
	key := identity + "@" + ip
	crmGuardMu.Lock()
	guard, exists := crmGuards[key]
	if !exists {
		random := make([]byte, 16)
		if _, err := rand.Read(random); err != nil {
			crmGuardMu.Unlock()
			return ctx, err
		}
		guard = &crmGuard{lease: hex.EncodeToString(random), ready: make(chan struct{}), refs: make(map[*crmGuardRef]bool)}
		crmGuards[key] = guard
	}
	crmGuardMu.Unlock()
	if !exists {
		allowed := crmGuardRequest("acquire", guard.lease, identity, ip)
		crmGuardMu.Lock()
		guard.allowed = allowed
		close(guard.ready)
		if !allowed && crmGuards[key] == guard {
			delete(crmGuards, key)
		}
		crmGuardMu.Unlock()
		if allowed {
			go crmGuardMonitor(key, guard, identity, ip)
		}
	}
	<-guard.ready
	crmGuardMu.Lock()
	if !guard.allowed {
		crmGuardMu.Unlock()
		return ctx, fmt.Errorf("CRM connection quota exceeded")
	}
	guarded, cancel := context.WithCancel(ctx)
	reference := &crmGuardRef{cancel: cancel}
	guard.refs[reference] = true
	crmGuardMu.Unlock()
	crmGuardAttach(guarded, key, guard, identity, ip, reference)
	return guarded, nil
}

// Each stream gets a unique reference object with nonzero size.
type crmGuardRef struct{ cancel context.CancelFunc }

func crmGuardAttach(ctx context.Context, key string, guard *crmGuard, identity, ip string, reference *crmGuardRef) {
	context.AfterFunc(ctx, func() {
		crmGuardMu.Lock()
		delete(guard.refs, reference)
		empty := len(guard.refs) == 0
		if empty {
			if crmGuards[key] == guard {
				delete(crmGuards, key)
			}
			guard.allowed = false
		}
		crmGuardMu.Unlock()
		if empty {
			crmGuardRequest("release", guard.lease, identity, ip)
		}
	})
}

func crmGuardMonitor(key string, guard *crmGuard, identity, ip string) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for range ticker.C {
		crmGuardMu.Lock()
		alive := guard.allowed && crmGuards[key] == guard
		crmGuardMu.Unlock()
		if !alive {
			return
		}
		if crmGuardRequest("check", guard.lease, identity, ip) {
			continue
		}
		crmGuardMu.Lock()
		guard.allowed = false
		if crmGuards[key] == guard {
			delete(crmGuards, key)
		}
		cancels := []context.CancelFunc{}
		for reference := range guard.refs {
			cancels = append(cancels, reference.cancel)
		}
		crmGuardMu.Unlock()
		for _, cancel := range cancels {
			cancel()
		}
		return
	}
}
