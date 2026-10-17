/* ==========================================================================
   Cybercab Forum — seed content
   --------------------------------------------------------------------------
   IMPORTANT: everything below is FICTIONAL demo data written for development.
   These are not real posts, not real quotes, and not real people. Handles are
   invented. Timestamps are relative to first load so the forum always looks
   freshly active.
   ========================================================================== */

window.SEED = {

  categories: [
    { id: "news",      name: "Announcements",            color: "#e0a33e", blurb: "Service areas, launches, and official word." },
    { id: "rides",     name: "Rides & Routes",           color: "#5ec8ff", blurb: "Trip reports, wait times, and zone chatter." },
    { id: "fsd",       name: "FSD & Autonomy",           color: "#a78bfa", blurb: "Unsupervised driving, edge cases, software versions." },
    { id: "pricing",   name: "Pricing & Economics",      color: "#4ec9a0", blurb: "Per-mile costs, surge behaviour, unit economics." },
    { id: "charging",  name: "Charging & Depots",        color: "#ff8f5e", blurb: "Wireless pads, turnaround time, fleet uptime." },
    { id: "ownership", name: "Ownership & Reservations", color: "#f472b6", blurb: "Delivery timelines, reservations, buying questions." },
    { id: "design",    name: "Design & Engineering",     color: "#94a3b8", blurb: "Hardware, materials, and teardown talk." },
    { id: "lounge",    name: "Off-Topic Lounge",         color: "#7c8aa5", blurb: "Everything else." }
  ],

  threads: [
    {
      id: "t1", cat: "news", pinned: true, author: "gridwatch", hoursAgo: 3, views: 2841, votes: 96,
      title: "Austin service zone quietly expands north past Round Rock",
      body: "The coverage layer in the app now shades a noticeably wider northern boundary than the one published at launch. The new edge appears to cut along 1431 rather than looping back at Wells Branch.\n\nAnyone else seeing the same polygon, or is my app cache stale?",
      replies: [
        { author: "atx_regular", hoursAgo: 2, votes: 22, body: "Same polygon here. Took a trip out to Round Rock yesterday and it never asked me to confirm the pickup address, which it used to do outside the zone." },
        { author: "gridwatch", hoursAgo: 1, votes: 14, body: "That matches what I saw. So the in-app coverage layer and the published map are definitively out of sync right now." },
        { author: "mod_cyber", hoursAgo: 1, votes: 9, body: "Pinned for visibility. If anybody has screenshots of the old boundary, post them. Before and after makes this much easier to track over time." },
        { author: "wetroad", hoursAgo: 0.4, votes: 6, body: "Worth noting the app caches that layer. Force a refresh before you compare, or you will report a change that is not really there." }
      ]
    },
    {
      id: "t2", cat: "news", author: "atx_regular", hoursAgo: 9, views: 1620, votes: 61,
      title: "Dallas launch: what the Austin playbook tells us about timing",
      body: "If the pattern holds, there is roughly a three week gap between the first public sighting of a service-area outline and paid rides actually opening. Austin went from permit chatter to paid rides on September 3.\n\nWorth watching the same signals for Dallas rather than guessing from press coverage.",
      replies: [
        { author: "dfw_bound", hoursAgo: 7, votes: 18, body: "Two transporter loads of cars parked near downtown last week. Anecdotal, but it fits your timeline." },
        { author: "regwatch", hoursAgo: 6, votes: 31, body: "The regulatory piece matters more than the logistics. Unsupervised operation in a new state is not a copy-paste job." },
        { author: "nightshift", hoursAgo: 4, votes: 12, body: "Different state, different regulator, different argument. I would add a couple of weeks to your estimate." }
      ]
    },
    {
      id: "t3", cat: "news", author: "regwatch", hoursAgo: 26, views: 3120, votes: 128,
      title: "Certification audit: sworn answers due October 30",
      body: "The audit concerns how the exemption path for a vehicle with no steering wheel was certified. It is not about whether the cars drive well.\n\nThat distinction matters, because the remedy for a paperwork problem is usually documentation rather than a grounding.",
      replies: [
        { author: "stacktrace", hoursAgo: 24, votes: 27, body: "This is the most reasonable framing I have seen on the topic. Everyone online wants it to be a hardware story." },
        { author: "gridwatch", hoursAgo: 22, votes: 15, body: "Agreed. The interesting part is the disclosure schedule, not the headline." },
        { author: "patientzero", hoursAgo: 20, votes: 19, body: "Has any analyst publicly asked what happens to the Dallas timeline if the answers slip past the deadline?" },
        { author: "regwatch", hoursAgo: 18, votes: 24, body: "Not that I can find. Which is itself a signal about how thin the coverage is." }
      ]
    },
    {
      id: "t4", cat: "rides", author: "austin_commuter", hoursAgo: 5, views: 980, votes: 44,
      title: "Twelve rides this week: a wait-time log",
      body: "Median wait came out at 4m10s across twelve trips, with one 11 minute outlier at 5pm on Wednesday.\n\nThe surprising part: short trips under two miles were consistently the slowest to match, which is the opposite of what I expected going in.",
      replies: [
        { author: "atx_regular", hoursAgo: 4, votes: 16, body: "Short trips being slow to match makes sense if the fleet is staging to maximise miles per repositioning event." },
        { author: "numbersguy", hoursAgo: 3, votes: 11, body: "That should show up in your per-mile cost as well. Were the short trips more expensive per mile for you?" },
        { author: "austin_commuter", hoursAgo: 2, votes: 13, body: "Noticeably, yes. Roughly 1.4x the per-mile rate on the trips under two miles." }
      ]
    },
    {
      id: "t5", cat: "rides", author: "wetroad", hoursAgo: 20, views: 1440, votes: 52,
      title: "Rain behaviour at night: two disengagements in one trip",
      body: "Both events were at unlit intersections with standing water and worn lane markings. The car did the procedurally correct thing, pulling over and asking for guidance, but the second one left me on a shoulder with 45mph traffic, which felt considerably worse than the first.",
      replies: [
        { author: "yieldbot", hoursAgo: 18, votes: 21, body: "Where it stops matters as much as why it stops. A narrow shoulder next to 45mph traffic is a bad answer even if it is technically a safe state." },
        { author: "stacktrace", hoursAgo: 16, votes: 9, body: "Was there a remote operator on the line, or was it a recorded prompt?" },
        { author: "wetroad", hoursAgo: 15, votes: 12, body: "Live, with a noticeable delay. Under a minute, but it felt a lot longer sitting there." }
      ]
    },
    {
      id: "t6", cat: "rides", author: "dfw_bound", hoursAgo: 48, views: 760, votes: 29,
      title: "Airport pickups still excluded from the service area",
      body: "Both the Austin and Dallas outlines approach the terminal but exclude the pickup curb itself. That leaves the single highest-demand trip type in any city off the table.",
      replies: [
        { author: "fleetguy", hoursAgo: 24, votes: 17, body: "Airport curbs are almost always a separate permit with a separate fee structure. It is not purely a technical boundary." }
      ]
    },
    {
      id: "t7", cat: "fsd", author: "stacktrace", hoursAgo: 7, views: 2210, votes: 87,
      title: "Unsupervised build: what actually changed in ride quality",
      body: "The headline is smoother longitudinal control. Far less of the late braking that made the previous build feel jumpy in stop-and-go traffic.\n\nThe unresolved item is still unprotected left turns with a stale gap estimate on oncoming traffic.",
      replies: [
        { author: "yieldbot", hoursAgo: 6, votes: 23, body: "Late braking was the single biggest comfort complaint I heard from first-time riders. Fixing that is worth more than any new capability." },
        { author: "wetroad", hoursAgo: 5, votes: 14, body: "I still saw a hesitation on a protected left with a pedestrian near the corner. Brief, but it read as uncertainty rather than caution." },
        { author: "stacktrace", hoursAgo: 4, votes: 18, body: "That tracks. Confidence looks more consistent, but the tail cases have not moved much." }
      ]
    },
    {
      id: "t8", cat: "fsd", author: "yieldbot", hoursAgo: 24, views: 1180, votes: 41,
      title: "Left turns across traffic remain the weak spot",
      body: "Every uncomfortable moment I have logged in six months of riding traces back to judging the gap in oncoming traffic.\n\nIt is a genuinely hard problem and the failure mode is conservative, which is the right bias. But it is still the thing that makes rides feel uneven.",
      replies: [
        { author: "regwatch", hoursAgo: 22, votes: 20, body: "Conservative and uneven is a reasonable trade for a while. The failure mode nobody wants is decisive and wrong." }
      ]
    },
    {
      id: "t9", cat: "pricing", author: "numbersguy", hoursAgo: 12, views: 1760, votes: 73,
      title: "Per-mile spreadsheet after sixty paid rides",
      body: "Effective cost to me landed in the low thirties per mile, with surge on late-night trips doing most of the damage to the average.\n\nRemoving the 2am trips entirely drops the average by about a fifth.",
      replies: [
        { author: "austin_commuter", hoursAgo: 10, votes: 19, body: "That matches my anecdotal sense. The daytime product is competitive, the late-night product is not." },
        { author: "nightshift", hoursAgo: 9, votes: 17, body: "From the other side of it: the late-night premium is the only reason a car is positioned anywhere near me at 2am at all." }
      ]
    },
    {
      id: "t10", cat: "pricing", author: "nightshift", hoursAgo: 72, views: 890, votes: 33,
      title: "Surge at 2am is real: 1.9x on a four-mile trip",
      body: "Same route, same night of the week, roughly double the daytime fare. I am not arguing it is unfair, only that anybody planning a night out should budget for it.",
      replies: [
        { author: "numbersguy", hoursAgo: 48, votes: 14, body: "Post both receipts if you still have them. Clean pairs like that are rare and genuinely useful." }
      ]
    },
    {
      id: "t11", cat: "charging", author: "fluxloop", hoursAgo: 6, views: 1020, votes: 45,
      title: "Wireless pad efficiency measured at roughly 87 percent",
      body: "Wall-to-battery measurement across eleven sessions on the same pad. 87 percent average, best case 90 percent when the car was already well aligned from a previous session.\n\nMisalignment is where the losses concentrate.",
      replies: [
        { author: "depot_nerd", hoursAgo: 5, votes: 22, body: "Alignment losses are the whole story in depot economics. A pad that needs a human to nudge the car is not an autonomous pad." },
        { author: "fluxloop", hoursAgo: 4, votes: 16, body: "Exactly. The self-park accuracy has to be good enough that the pad is never doing the correction work." }
      ]
    },
    {
      id: "t12", cat: "charging", author: "depot_nerd", hoursAgo: 48, views: 640, votes: 26,
      title: "Depot turnaround: nine minutes from arrival to available",
      body: "Watched a depot for an afternoon. Arrival to back-online averaged nine minutes, and most of that was the drive-through queue rather than charging itself.",
      replies: [
        { author: "fluxloop", hoursAgo: 30, votes: 15, body: "Queue time is the number nobody publishes. Throughput per bay is a far more honest metric than peak charge rate." }
      ]
    },
    {
      id: "t13", cat: "ownership", author: "patientzero", hoursAgo: 96, views: 1320, votes: 38,
      title: "Reservation since October 2024 and still no invite",
      body: "I am not upset about the wait. I am frustrated that there is no way to know whether I am early or whether my reservation is effectively void.",
      replies: [
        { author: "fleetguy", hoursAgo: 72, votes: 20, body: "Consumer reservations and fleet orders are almost certainly two separate queues, and the fleet side is going to win for a while." },
        { author: "patientzero", hoursAgo: 70, votes: 25, body: "Which is completely fine, but say so. The silence is the part that costs goodwill." }
      ]
    },
    {
      id: "t14", cat: "design", author: "designfirst", hoursAgo: 8, views: 1900, votes: 98,
      title: "Two seats is the entire thesis: change my mind",
      body: "Every compromise in this vehicle traces back to a deliberate bet that most paid trips carry one or two people.\n\nIf that bet is right, everything else is downstream of it. If it is wrong, no amount of polish rescues the product.",
      replies: [
        { author: "fleetguy", hoursAgo: 7, votes: 21, body: "It is right on the distribution and wrong on the exceptions. Families and airport luggage both exist, and those trips go to a different product." },
        { author: "gridwatch", hoursAgo: 6, votes: 18, body: "That is the honest trade. You are building for the mode, not the mean." },
        { author: "designfirst", hoursAgo: 5, votes: 15, body: "Agreed, and that is exactly why the storage question matters more than the seat count." }
      ]
    },
    {
      id: "t15", cat: "ownership", author: "fleetguy", hoursAgo: 24, views: 720, votes: 21,
      title: "Insurance quotes for commercial use: any real data?",
      body: "Trying to model a small fleet and the quotes I am getting vary by a factor of three with no explanation of the assumptions behind them.",
      replies: [
        { author: "numbersguy", hoursAgo: 20, votes: 13, body: "Ask each one for the mileage assumption and the liability limit they priced against. That usually explains most of the spread." }
      ]
    },
    {
      id: "t16", cat: "lounge", author: "weekendwarrior", hoursAgo: 30, views: 560, votes: 18,
      title: "What are you all driving while you wait?",
      body: "Genuinely curious what the crowd here is driving in the meantime, and whether anyone has actually downsized in anticipation.",
      replies: [
        { author: "atx_regular", hoursAgo: 28, votes: 11, body: "Sold the second car and have not missed it. Rides plus one vehicle has held up for eight months." },
        { author: "wetroad", hoursAgo: 26, votes: 8, body: "Kept both. Weather days are the reason." }
      ]
    }
  ]
};
