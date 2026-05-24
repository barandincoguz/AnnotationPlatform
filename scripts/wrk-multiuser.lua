-- wrk script for multi-user authenticated load against /api/feed.
--
-- Reads cookie values (one per line, no "anotasyon_session=" prefix) from
-- the file pointed at by env var WRK_COOKIES_FILE, then on every request
-- picks one cookie at random and sends it as the session.

local cookies = {}
local thread_id = 0
local thread_counter = 0

-- setup(thread) runs once per thread in the main Lua state before the
-- thread is dispatched. We use it to inject a per-thread numeric id that
-- the thread can read inside init() for a unique RNG seed.
function setup(thread)
    thread_counter = thread_counter + 1
    thread:set("thread_id", thread_counter)
end

function init(args)
    local path = os.getenv("WRK_COOKIES_FILE")
    if not path or path == "" then
        io.stderr:write("WRK_COOKIES_FILE env var not set\n")
        os.exit(1)
    end
    local f, err = io.open(path, "r")
    if not f then
        io.stderr:write("failed to open " .. path .. ": " .. tostring(err) .. "\n")
        os.exit(1)
    end
    for line in f:lines() do
        if line and line ~= "" then
            cookies[#cookies + 1] = line
        end
    end
    f:close()
    if #cookies == 0 then
        io.stderr:write("no cookies found in " .. path .. "\n")
        os.exit(1)
    end
    -- thread_id is set in setup() and copied into each thread's Lua state.
    -- Fall back to 0 if absent (e.g. -t1 with no setup invocation).
    math.randomseed(os.time() + (thread_id or 0))
end

function request()
    local idx = math.random(#cookies)
    return wrk.format("GET", nil, {
        ["Cookie"] = "anotasyon_session=" .. cookies[idx],
        ["Accept"] = "application/json",
    })
end
