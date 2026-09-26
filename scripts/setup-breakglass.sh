#!/bin/bash
# setup-breakglass.sh -- create/refresh ONE shared break-glass local admin in every SSO-protected
# app, so each can still be reached when the identity provider (Authentik here) is down.
# Covers Jellyfin, Immich, Open WebUI, Grafana, Homarr (v1) and Portainer CE. Idempotent; tests a
# real login as the break-glass user in every app and prints only OK/FAIL (never a password).
# Portainer: with OAuth enabled only the INITIAL admin (id 1) may log in locally, so the script
# renames that account instead of adding a new one.
# Tested 2026-09-26 against Jellyfin 10.11.11, Immich 3.2, Open WebUI 0.11.4, Grafana (TeslaMate's
# bundled image), Homarr 1.77, Portainer CE 2.45. Proxmox VE / PBS were deliberately left on root@pam.
#   sudo bash setup-breakglass.sh
set -u
exec python3 - "$@" <<'PY'
import re, json, ssl, sqlite3, urllib.request, urllib.parse, http.cookiejar

# ---- EDIT THESE for your setup ------------------------------------------------------------
MEDIA, MEDIA_TLS, AI = 'http://<media-lxc-ip>', 'https://<media-lxc-ip>', 'http://<ai-lxc-ip>'
BREAKGLASS_USER, BREAKGLASS_EMAIL = '<breakglass-user>', '<breakglass-user>@<local-domain>'   # keep the username private
JELLYFIN_ADMIN = '<jellyfin-local-admin>'
IMMICH_ADMIN_EMAIL, OPENWEBUI_ADMIN_EMAIL, HOMARR_ADMIN = '<immich-local-admin-email>', '<openwebui-local-admin-email>', '<homarr-local-admin>'
HOMARR_DB = '<path-on-host-to>/homarr/appdata/db/db.sqlite'
# Secrets come from ONE root-only file of lines "{{NAME}} = value    <- comment" (keep every password
# in a single place). Names this script reads -- rename to match your own file:
#   PW_BREAKGLASS, PW_JELLYFIN_LOCAL, PW_IMMICH_LOCAL, PW_OPENWEBUI_LOCAL, PW_GRAFANA_ADMIN,
#   PW_HOMARR_ADMIN, PW_PORTAINER_ADMIN (only needed for the first run, before the rename)
SECRETS_FILE = '<path-to-your-root-only-secrets-file>'
# -------------------------------------------------------------------------------------------
IDX = dict(re.findall(r'^\{\{([A-Z_]+)\}\} +=\s*(.+?)    <- ', open(SECRETS_FILE).read(), re.M))
PW = IDX['PW_BREAKGLASS']
USER, EMAIL = BREAKGLASS_USER, BREAKGLASS_EMAIL
CTX = ssl._create_unverified_context()
RESULTS = []

def call(url, data=None, headers=None, method=None, jar=None, form=False, follow=True):
    h = dict(headers or {})
    if data is not None:
        if form:
            data = urllib.parse.urlencode(data).encode(); h.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        else:
            data = json.dumps(data).encode(); h.setdefault('Content-Type', 'application/json')
    hs = [urllib.request.HTTPSHandler(context=CTX)]
    if jar is not None: hs.append(urllib.request.HTTPCookieProcessor(jar))
    if not follow:
        class NoRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        hs.append(NoRedir())
    try:
        r = urllib.request.build_opener(*hs).open(urllib.request.Request(url, data=data, headers=h, method=method), timeout=20)
        body = r.read()
        try: body = json.loads(body)
        except Exception: pass
        return r.status, body
    except urllib.error.HTTPError as e:
        b = e.read()
        try: b = json.loads(b)
        except Exception: b = b[:200]
        return e.code, b
    except Exception as e:
        return 0, str(e)[:200]

def result(app, ok, note=''):
    RESULTS.append((app, ok)); print(f"{'OK  ' if ok else 'FAIL'} {app:12s} {note}", flush=True)

def step(app, fn):
    try: fn()
    except Exception as e: result(app, False, f'error: {type(e).__name__}: {str(e)[:150]}')

# ---------------------------------------------------------------- Jellyfin
def jellyfin():
    J = MEDIA + ':8096'
    base = 'MediaBrowser Client="breakglass-setup", Device="n5", DeviceId="breakglass-setup", Version="1"'
    c, b = call(J + '/Users/AuthenticateByName', {'Username': JELLYFIN_ADMIN, 'Pw': IDX['PW_JELLYFIN_LOCAL']}, {'Authorization': base})
    if c != 200: return result('Jellyfin', False, f'admin login failed ({c})')
    H = {'Authorization': base + f', Token="{b["AccessToken"]}"'}
    c, users = call(J + '/Users', headers=H)
    u = next((x for x in users if x['Name'].lower() == USER), None)
    if not u:
        c, u = call(J + '/Users/New', {'Name': USER, 'Password': PW}, H)
        if c != 200: return result('Jellyfin', False, f'create failed ({c})')
    else:
        call(J + f'/Users/{u["Id"]}/Password', {'NewPw': PW, 'ResetPassword': False}, H)
    c, full = call(J + f'/Users/{u["Id"]}', headers=H)
    pol = full['Policy']
    pol.update(IsAdministrator=True, IsDisabled=False, EnableAllFolders=True,
               AuthenticationProviderId='Jellyfin.Server.Implementations.Users.DefaultAuthenticationProvider',
               PasswordResetProviderId='Jellyfin.Server.Implementations.Users.DefaultPasswordResetProvider')
    c, _ = call(J + f'/Users/{u["Id"]}/Policy', pol, H)
    if c not in (200, 204): return result('Jellyfin', False, f'policy failed ({c})')
    c, b = call(J + '/Users/AuthenticateByName', {'Username': USER, 'Pw': PW}, {'Authorization': base.replace('breakglass-setup', 'breakglass-test')})
    result('Jellyfin', c == 200 and b['User']['Policy']['IsAdministrator'], f'login as {USER}: {c}, admin={c == 200 and b["User"]["Policy"]["IsAdministrator"]}')

# ---------------------------------------------------------------- Immich
def immich():
    I = MEDIA + ':2283/api'
    c, b = call(I + '/auth/login', {'email': IMMICH_ADMIN_EMAIL, 'password': IDX['PW_IMMICH_LOCAL']})
    if c not in (200, 201): return result('Immich', False, f'admin login failed ({c})')
    H = {'Authorization': 'Bearer ' + b['accessToken']}
    c, users = call(I + '/admin/users', headers=H)
    u = next((x for x in users if x['email'].lower() == EMAIL), None)
    if not u:
        c, u = call(I + '/admin/users', {'email': EMAIL, 'name': USER, 'password': PW, 'isAdmin': True, 'shouldChangePassword': False, 'notify': False}, H)
        if c not in (200, 201): return result('Immich', False, f'create failed ({c}) {u}')
    else:
        c, _ = call(I + f'/admin/users/{u["id"]}', {'password': PW, 'isAdmin': True, 'shouldChangePassword': False}, H, method='PUT')
    c, b = call(I + '/auth/login', {'email': EMAIL, 'password': PW})
    result('Immich', c in (200, 201) and b.get('isAdmin'), f'login as {EMAIL}: {c}, admin={b.get("isAdmin") if isinstance(b, dict) else None}')

# ---------------------------------------------------------------- Open WebUI
def openwebui():
    O = AI + ':3005/api/v1'
    c, b = call(O + '/auths/signin', {'email': EMAIL, 'password': PW})
    if c == 200 and b.get('role') == 'admin':
        return result('Open WebUI', True, f'login as {EMAIL}: 200, role=admin (already existed)')
    c, a = call(O + '/auths/signin', {'email': OPENWEBUI_ADMIN_EMAIL, 'password': IDX['PW_OPENWEBUI_LOCAL']})
    if c != 200: return result('Open WebUI', False, f'admin login failed ({c})')
    H = {'Authorization': 'Bearer ' + a['token']}
    c, r = call(O + '/auths/add', {'name': USER, 'email': EMAIL, 'password': PW, 'role': 'admin'}, H)
    if c != 200:
        # already exists with another password/role: find it and update
        c2, lst = call(O + '/users/all', headers=H)
        users = lst.get('users', lst) if isinstance(lst, dict) else lst
        u = next((x for x in (users or []) if x.get('email', '').lower() == EMAIL), None)
        if not u: return result('Open WebUI', False, f'create failed ({c}) {str(r)[:120]}')
        call(O + f'/users/{u["id"]}/update', {'name': USER, 'email': EMAIL, 'password': PW, 'role': 'admin', 'profile_image_url': u.get('profile_image_url', '/user.png')}, H)
    c, b = call(O + '/auths/signin', {'email': EMAIL, 'password': PW})
    result('Open WebUI', c == 200 and b.get('role') == 'admin', f'login as {EMAIL}: {c}, role={b.get("role") if isinstance(b, dict) else None}')

# ---------------------------------------------------------------- Grafana
def grafana():
    G = MEDIA + ':3002'
    jar = http.cookiejar.CookieJar()
    O = {'Origin': G}
    c, _ = call(G + '/login', {'user': 'admin', 'password': IDX['PW_GRAFANA_ADMIN']}, O, jar=jar)
    if c != 200: return result('Grafana', False, f'admin login failed ({c})')
    c, u = call(G + f'/api/users/lookup?loginOrEmail={USER}', headers=O, jar=jar)
    if c == 404:
        c, u = call(G + '/api/admin/users', {'name': USER, 'login': USER, 'email': EMAIL, 'password': PW, 'OrgId': 1}, O, jar=jar)
        if c != 200: return result('Grafana', False, f'create failed ({c}) {u}')
    else:
        call(G + f'/api/admin/users/{u["id"]}/password', {'password': PW}, O, method='PUT', jar=jar)
    uid = u['id']
    call(G + f'/api/admin/users/{uid}/permissions', {'isGrafanaAdmin': True}, O, method='PUT', jar=jar)
    c3, _ = call(G + f'/api/org/users/{uid}', {'role': 'Admin'}, O, method='PATCH', jar=jar)
    j2 = http.cookiejar.CookieJar()
    c, _ = call(G + '/login', {'user': USER, 'password': PW}, O, jar=j2)
    c2, me = call(G + '/api/user', headers=O, jar=j2)
    ok = c == 200 and c2 == 200 and me.get('isGrafanaAdmin')
    result('Grafana', ok, f'login as {USER}: {c}, server-admin={me.get("isGrafanaAdmin") if isinstance(me, dict) else None}, org-role set: {c3}')

# ---------------------------------------------------------------- Homarr
def homarr():
    H = MEDIA + ':7575'
    dbp = HOMARR_DB
    con = sqlite3.connect(f'file:{dbp}?mode=ro', uri=True)
    gid = con.execute("select id from \"group\" where name='credentials-admin'").fetchone()[0]
    exists = con.execute("select count(*) from user where name=? and provider='credentials'", (USER,)).fetchone()[0]
    con.close()
    def login(name, pw):
        jar = http.cookiejar.CookieJar()
        c, b = call(H + '/api/auth/csrf', jar=jar)
        call(H + '/api/auth/callback/credentials', {'csrfToken': b['csrfToken'], 'name': name, 'password': pw, 'json': 'true'}, form=True, jar=jar, follow=False)
        return jar, any('session-token' in ck.name for ck in jar)
    if not exists:
        jar, ok = login(HOMARR_ADMIN, IDX['PW_HOMARR_ADMIN'])
        if not ok: return result('Homarr', False, 'admin login failed')
        c, b = call(H + '/api/trpc/user.create', {'json': {'username': USER, 'email': '', 'password': PW, 'confirmPassword': PW, 'groupIds': [gid]}}, {'Origin': H}, jar=jar)
        if c != 200: return result('Homarr', False, f'create failed ({c}) {str(b)[:160]}')
    jar, ok = login(USER, PW)
    con = sqlite3.connect(f'file:{dbp}?mode=ro', uri=True)
    grp = con.execute("select group_concat(g.name) from user u join groupMember gm on gm.user_id=u.id join \"group\" g on g.id=gm.group_id where u.name=?", (USER,)).fetchone()[0]
    con.close()
    note = '' if not exists else ' (already existed; password NOT re-applied -- reset it in Homarr if login fails)'
    result('Homarr', ok and 'credentials-admin' in (grp or ''), f'login as {USER}: {ok}, groups={grp}{note}')

# ---------------------------------------------------------------- Portainer
def portainer():
    P = MEDIA_TLS + ':9443/api'
    c, b = call(P + '/auth', {'Username': USER, 'Password': PW})
    if c == 200:
        H = {'Authorization': 'Bearer ' + b['jwt']}
        c2, u = call(P + '/users/1', headers=H)
        return result('Portainer', u.get('Username') == USER and u.get('Role') == 1, f'login as {USER}: 200, is initial admin (id 1) role={u.get("Role")} (already done)')
    c, b = call(P + '/auth', {'Username': 'admin', 'Password': IDX.get('PW_PORTAINER_ADMIN', '')})
    if c != 200: return result('Portainer', False, f'admin login failed ({c})')
    H = {'Authorization': 'Bearer ' + b['jwt']}
    c, u = call(P + '/users/1', headers=H)
    if u.get('Username') != 'admin' or u.get('Role') != 1: return result('Portainer', False, f'user id 1 is not the admin account: {u.get("Username")}')
    c, r = call(P + '/users/1', {'Username': USER, 'NewPassword': PW}, H, method='PUT')
    if c != 200: return result('Portainer', False, f'rename/password failed ({c}) {r}')
    c, b = call(P + '/auth', {'Username': USER, 'Password': PW})
    result('Portainer', c == 200, f'renamed initial admin -> {USER}; login as {USER}: {c}')

for name, fn in (('Jellyfin', jellyfin), ('Immich', immich), ('Open WebUI', openwebui), ('Grafana', grafana), ('Homarr', homarr), ('Portainer', portainer)):
    step(name, fn)
print(f"\n{sum(ok for _, ok in RESULTS)}/{len(RESULTS)} apps have a working break-glass '{USER}' admin")
PY
