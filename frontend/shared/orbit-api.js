/* Jagran Orbit client for the Flask backend.
 *
 *  - OrbitAPI.loadData()   the event feed -> window.ORBIT_DATA (API first, bundled snapshot if the API is down)
 *  - OrbitAPI.start(src)   owner page: load feed + workspace, then load the app script
 *  - OrbitAPI.ready(fn)    other pages: load feed, then run fn
 *  - OrbitStore            load/save/remove for the owner's sector, profile and tasks. Writes go to
 *                          localStorage at once and to the database in the background, so the page works
 *                          offline and catches up when the server is back.
 *
 * Opened from disk (file://) there is no server, so everything stays in localStorage as before.
 */
(function () {
  'use strict';

  var SECTORS = ['Automotive', 'Energy', 'Banking', 'Pharma', 'Technology', 'FMCG & Food', 'Agriculture', 'Real Estate', 'Cement & Infra', 'Metals & Mining', 'Aviation & Travel', 'Telecom & Media', 'Retail & E-commerce', 'Consumer Durables', 'Gems & Jewellery'];
  var DIRTY_KEY = 'orbit_sync_dirty';
  var here = (document.currentScript && document.currentScript.src) || '';
  var SNAPSHOT = here.replace(/\/shared\/orbit-api\.js.*$/, '/owner/data/events.js');
  var BASE = typeof window.ORBIT_API_BASE === 'string' ? window.ORBIT_API_BASE.replace(/\/$/, '')
    : (location.protocol === 'http:' || location.protocol === 'https:') ? '' : null;
  var online = BASE !== null;

  function ls(op, key, val) {
    try {
      if (op === 'get') return localStorage.getItem(key);
      if (op === 'set') localStorage.setItem(key, val);
      if (op === 'del') localStorage.removeItem(key);
    } catch (e) { /* private mode or quota: keep going in memory */ }
    return null;
  }
  function lsJSON(key, fallback) {
    var raw = ls('get', key);
    if (!raw) return fallback;
    try { return JSON.parse(raw); } catch (e) { return fallback; }
  }
  function request(method, path, body) {
    // keepalive lets a save still go out while the tab is closing.
    var opts = { method: method, credentials: 'same-origin', headers: {}, keepalive: method !== 'GET' };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(BASE + '/api' + path, opts).then(function (r) {
      if (!r.ok) { var e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
      return r.status === 204 ? null : r.json();
    });
  }
  function script(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src; s.onload = resolve; s.onerror = function () { reject(new Error('Could not load ' + src)); };
      document.head.appendChild(s);
    });
  }
  function notify(state) {
    try { window.dispatchEvent(new CustomEvent('orbit:sync', { detail: { state: state } })); } catch (e) { /* old browser */ }
  }
  function banner(text) {
    var el = document.createElement('div');
    el.setAttribute('role', 'status');
    el.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99;padding:8px 14px;background:#fff4d6;color:#5c4400;font:13px system-ui,sans-serif;text-align:center;border-top:1px solid #e6c766';
    el.textContent = text;
    document.body.appendChild(el);
  }

  /* ----------------------------------------------------------------- feed */
  var dataPromise = null;
  function loadData() {
    if (dataPromise) return dataPromise;
    dataPromise = (online
      ? fetch(BASE + '/api/data', { cache: 'no-cache', credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (d) { window.ORBIT_DATA = d; window.ORBIT_SOURCE = 'api'; })
      : Promise.reject(new Error('offline'))
    ).catch(function () {
      return script(SNAPSHOT).then(function () {
        window.ORBIT_SOURCE = 'snapshot';
        if (online) banner('The live feed is unavailable. Showing the saved snapshot.');
      });
    });
    return dataPromise;
  }

  /* ---------------------------------------------------------------- store */
  var mem = {};
  var dirty = lsJSON(DIRTY_KEY, {});   // key -> 'put' | 'del'  (changes the server has not confirmed yet)
  var timer = null, flushing = false;

  function route(key) {
    var m;
    if (key === 'orbit_owner_sector') return { path: '/workspace/sector', body: function (v) { return { sector: v }; } };
    if ((m = /^orbit_owner_profile_(.+)$/.exec(key))) return { path: '/workspace/profile/' + encodeURIComponent(m[1]), del: '/workspace/' + encodeURIComponent(m[1]) + '?part=profile', body: function (v) { return v; } };
    if ((m = /^orbit_owner_tasks_(.+)$/.exec(key))) return { path: '/workspace/tasks/' + encodeURIComponent(m[1]), del: '/workspace/' + encodeURIComponent(m[1]) + '?part=tasks', body: function (v) { return v; } };
    return null;
  }
  function saveDirty() { ls('set', DIRTY_KEY, JSON.stringify(dirty)); }
  function mark(key, op) {
    if (!online || !route(key)) return;
    dirty[key] = op; saveDirty(); notify('pending');
    clearTimeout(timer); timer = setTimeout(flush, 400);
  }
  function flush() {
    if (!online || flushing) return Promise.resolve();
    var keys = Object.keys(dirty);
    if (!keys.length) return Promise.resolve();
    flushing = true;
    var chain = Promise.resolve(), failed = false;
    keys.forEach(function (key) {
      chain = chain.then(function () {
        var r = route(key), op = dirty[key];
        if (!r) { delete dirty[key]; return; }
        var call = op === 'del' ? request('DELETE', r.del) : request('PUT', r.path, r.body(mem[key]));
        return call.then(function () { if (dirty[key] === op) delete dirty[key]; })
          .catch(function (e) {
            // The server rejected the data (4xx): retrying will not help, so stop tracking it.
            if (e.status && e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) delete dirty[key];
            else failed = true;
          });
      });
    });
    return chain.then(function () {
      flushing = false; saveDirty();
      if (failed) { notify('offline'); clearTimeout(timer); timer = setTimeout(flush, 15000); }
      else { notify('saved'); if (Object.keys(dirty).length) flush(); }
    });
  }

  var Store = {
    load: function (key, fallback) {
      if (Object.prototype.hasOwnProperty.call(mem, key)) return mem[key];
      return lsJSON(key, fallback);
    },
    save: function (key, val) {
      mem[key] = val;
      ls('set', key, JSON.stringify(val));
      mark(key, 'put');
      return true;
    },
    remove: function (key) {
      delete mem[key];
      ls('del', key);
      mark(key, 'del');
    },
    flush: flush
  };

  /* Pull the workspace from the server. A brand-new workspace adopts whatever this browser
     already had in localStorage (so existing owners keep their numbers); after that the
     server is the source of truth, except for edits made offline that are still pending. */
  function hydrate() {
    if (!online) return Promise.resolve();
    return request('GET', '/workspace').then(function (snap) {
      var fresh = !Object.keys(snap.profiles).length && !Object.keys(snap.tasks).length;
      var server = { orbit_owner_sector: snap.sector };
      SECTORS.forEach(function (s) {
        if (snap.profiles[s]) server['orbit_owner_profile_' + s] = snap.profiles[s];
        if (snap.tasks[s]) server['orbit_owner_tasks_' + s] = snap.tasks[s];
      });
      var keys = ['orbit_owner_sector'];
      SECTORS.forEach(function (s) { keys.push('orbit_owner_profile_' + s, 'orbit_owner_tasks_' + s); });
      keys.forEach(function (key) {
        var local = lsJSON(key, undefined);
        var op = dirty[key];
        if (op === 'del') { delete mem[key]; return; }                       // offline reset still to send
        if (op === 'put' && local !== undefined) { mem[key] = local; return; } // offline edit still to send
        if (fresh && local !== undefined) { mem[key] = local; dirty[key] = 'put'; return; } // first visit: adopt local
        if (server[key] !== undefined) { mem[key] = server[key]; ls('set', key, JSON.stringify(server[key])); }
        else { delete mem[key]; ls('del', key); }
      });
      saveDirty();
      return flush();
    }).catch(function () {
      // Server unreachable: carry on from localStorage; queued edits are retried by flush().
      notify('offline');
    });
  }

  window.addEventListener('online', function () { flush(); });
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(); });

  /* --------------------------------------------------------------- start */
  function fail(err) {
    var view = document.getElementById('view') || document.body;
    view.innerHTML = '<div style="padding:40px;font:15px system-ui,sans-serif;color:#10243b"><strong>Jagran Orbit could not start.</strong><p>' +
      String(err && err.message || err).replace(/[<&]/g, '') + '</p><p>Start the backend with <code>python run.py</code> in <code>backend/</code>, or open the page again.</p></div>';
  }

  window.OrbitStore = Store;
  window.OrbitAPI = {
    loadData: loadData,
    ready: function (fn) { loadData().then(fn).catch(fail); },
    start: function (appScript) {
      var view = document.getElementById('view');
      if (view) view.innerHTML = '<div style="padding:40px;color:#51657a;font:15px system-ui,sans-serif">Loading your workspace...</div>';
      Promise.all([loadData(), hydrate()]).then(function () { return script(appScript); }).catch(fail);
    },
    request: request,
    get online() { return online; }
  };
})();
