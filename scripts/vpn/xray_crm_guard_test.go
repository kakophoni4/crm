package dispatcher

import (
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "sync"
    "testing"
    "time"
    "github.com/xtls/xray-core/common/net"
    "github.com/xtls/xray-core/common/protocol"
    "github.com/xtls/xray-core/common/session"
)

func TestCRMGuard(t *testing.T) {
    var mu sync.Mutex
    acquisitions, releases := 0, 0
    denyCheck := false
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        var body map[string]string
        if json.NewDecoder(r.Body).Decode(&body) != nil { t.Error("invalid request"); return }
        mu.Lock(); defer mu.Unlock()
        allowed := body["ip"] != "203.0.113.4"
        if body["action"] == "acquire" { acquisitions++ }
        if body["action"] == "release" { releases++; allowed = false }
        if body["action"] == "check" && denyCheck { allowed = false }
        json.NewEncoder(w).Encode(map[string]bool{"allowed": allowed})
    }))
    defer server.Close()
    crmGuardURL = server.URL
    crmGuardEnabled = true
    inbound := func(parent context.Context, ip string) context.Context {
        return session.ContextWithInbound(parent, &session.Inbound{User: &protocol.MemoryUser{Email: "crm-vpn-83f12507-1856-4008-8715-1c42c9101128"}, Source: net.TCPDestination(net.ParseAddress(ip), 10000)})
    }
    wait := func(expected int) {
        t.Helper()
        end := time.Now().Add(time.Second)
        for time.Now().Before(end) {
            mu.Lock(); count := releases; mu.Unlock()
            if count == expected { return }
            time.Sleep(time.Millisecond)
        }
        t.Fatal("lease not released")
    }
    first, cancelFirst := context.WithCancel(context.Background())
    second, cancelSecond := context.WithCancel(context.Background())
    if _, err := crmGuardContext(inbound(first, "203.0.113.1")); err != nil { t.Fatal(err) }
    if _, err := crmGuardContext(inbound(second, "203.0.113.1")); err != nil { t.Fatal(err) }
    mu.Lock(); count := acquisitions; mu.Unlock()
    if count != 1 { t.Fatal("same source IP must share an admission") }
    cancelFirst()
    time.Sleep(20 * time.Millisecond)
    mu.Lock(); count = releases; mu.Unlock()
    if count != 0 { t.Fatal("one live stream must retain the place") }
    cancelSecond(); wait(1)
    if _, err := crmGuardContext(inbound(context.Background(), "203.0.113.4")); err == nil { t.Fatal("rejected source must not get a link") }
    third, cancelThird := context.WithCancel(context.Background())
    defer cancelThird()
    guarded, err := crmGuardContext(inbound(third, "203.0.113.2"))
    if err != nil { t.Fatal(err) }
    mu.Lock(); denyCheck = true; mu.Unlock()
    select {
    case <-guarded.Done():
    case <-time.After(7 * time.Second): t.Fatal("revoked admission must cancel existing streams")
    }
    wait(2)
}
