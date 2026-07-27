(() => {
  // Web Audio Sound Synthesizer
  let audioCtx = null;

  function getAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playTone(freq, startTime, duration, type = "sine", gainValue = 0.2) {
    const ctx = getAudioContext();
    if (!ctx) return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = type;
    osc.frequency.setValueAtTime(freq, ctx.currentTime + startTime);

    gain.gain.setValueAtTime(gainValue, ctx.currentTime + startTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + startTime + duration);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(ctx.currentTime + startTime);
    osc.stop(ctx.currentTime + startTime + duration);
  }

  function playChoreCompleteSound(isEarly) {
    const ctx = getAudioContext();
    if (!ctx) return;

    if (isEarly) {
      // Extra special early complete sound: high energy sparkling fanfare
      // Notes: C5, E5, G5, C6, E6, G6, C7
      const notes = [523.25, 659.25, 783.99, 1046.50, 1318.51, 1567.98, 2093.00];
      notes.forEach((freq, idx) => {
        const t = idx * 0.05;
        playTone(freq, t, 0.25, "triangle", 0.25);
        playTone(freq * 1.005, t + 0.01, 0.2, "sine", 0.15);
      });

      // Sparkle sweep chime
      try {
        const sweepOsc = ctx.createOscillator();
        const sweepGain = ctx.createGain();
        sweepOsc.type = "sine";
        sweepOsc.frequency.setValueAtTime(800, ctx.currentTime);
        sweepOsc.frequency.exponentialRampToValueAtTime(2400, ctx.currentTime + 0.35);
        sweepGain.gain.setValueAtTime(0.12, ctx.currentTime);
        sweepGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        sweepOsc.connect(sweepGain);
        sweepGain.connect(ctx.destination);
        sweepOsc.start(ctx.currentTime);
        sweepOsc.stop(ctx.currentTime + 0.4);
      } catch (e) {
        // Fallback silently if sweep error
      }
    } else {
      // Standard chore completion sound: bright 4-note ascending arpeggio
      // Notes: E5, G#5, B5, E6
      const notes = [659.25, 830.61, 987.77, 1318.51];
      notes.forEach((freq, idx) => {
        const t = idx * 0.07;
        playTone(freq, t, 0.3, "sine", 0.22);
        playTone(freq * 0.5, t, 0.2, "triangle", 0.08);
      });
    }
  }

  function playAchievementSound(startOffset = 0) {
    const ctx = getAudioContext();
    if (!ctx) return;

    // Achievement level-up jingle fanfare
    // Notes: G4, C5, E5, G5, C6 (final note held longer with brassy warm feel)
    const notes = [
      { freq: 392.00, time: 0.00, duration: 0.15 },
      { freq: 523.25, time: 0.09, duration: 0.15 },
      { freq: 659.25, time: 0.18, duration: 0.15 },
      { freq: 783.99, time: 0.27, duration: 0.18 },
      { freq: 1046.50, time: 0.40, duration: 0.50 },
    ];

    notes.forEach((n) => {
      const t = startOffset + n.time;
      playTone(n.freq, t, n.duration, "triangle", 0.25);
      playTone(n.freq * 2, t, n.duration * 0.7, "sine", 0.12);
    });
  }

  const wrap = document.getElementById("celebration-wrap") || document.querySelector(".celebration-wrap");
  const timing = wrap ? wrap.dataset.timing : "";
  const hasUnlocks = wrap ? wrap.dataset.hasUnlocks === "true" : false;
  const isEarly = timing === "early";

  function triggerCelebrationSounds() {
    try {
      playChoreCompleteSound(isEarly);
      if (hasUnlocks) {
        // Play achievement sound 450ms after completion sound starts
        playAchievementSound(0.45);
      }
    } catch (e) {
      // Audio autoplay policy or hardware restriction
    }
  }

  // Attempt autoplay immediately
  triggerCelebrationSounds();

  // Mobile fallback: unlock audio on first touch/click if context was suspended
  const unlockAudioOnGesture = () => {
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume().then(() => {
        triggerCelebrationSounds();
      });
    }
    window.removeEventListener("pointerdown", unlockAudioOnGesture);
    window.removeEventListener("keydown", unlockAudioOnGesture);
  };
  window.addEventListener("pointerdown", unlockAudioOnGesture, { once: true });
  window.addEventListener("keydown", unlockAudioOnGesture, { once: true });

  // Replay sound button listener
  const replayBtn = document.getElementById("btn-replay-sound");
  if (replayBtn) {
    replayBtn.addEventListener("click", () => {
      triggerCelebrationSounds();
    });
  }

  // Confetti Animation
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.getElementById("confetti");
  if (canvas && !prefersReduced) {
    const ctx = canvas.getContext("2d");
    if (ctx) {
      const colors = ["#7c5cff", "#f472b6", "#34d399", "#fbbf24", "#60a5fa", "#f87171"];
      let w = 0;
      let h = 0;
      const particles = [];
      let frame = 0;
      const maxFrames = 90;

      function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
      }

      function spawn() {
        for (let i = 0; i < 80; i += 1) {
          particles.push({
            x: Math.random() * w,
            y: -20 - Math.random() * 40,
            r: 3 + Math.random() * 5,
            c: colors[(Math.random() * colors.length) | 0],
            vx: -2 + Math.random() * 4,
            vy: 2 + Math.random() * 4,
            rot: Math.random() * Math.PI,
            vr: -0.2 + Math.random() * 0.4,
          });
        }
      }

      function tick() {
        frame += 1;
        ctx.clearRect(0, 0, w, h);
        for (const p of particles) {
          p.x += p.vx;
          p.y += p.vy;
          p.vy += 0.08;
          p.rot += p.vr;
          ctx.save();
          ctx.translate(p.x, p.y);
          ctx.rotate(p.rot);
          ctx.fillStyle = p.c;
          ctx.fillRect(-p.r, -p.r / 2, p.r * 2, p.r);
          ctx.restore();
        }
        if (frame < maxFrames) {
          requestAnimationFrame(tick);
        } else {
          ctx.clearRect(0, 0, w, h);
        }
      }

      resize();
      window.addEventListener("resize", resize);
      spawn();
      requestAnimationFrame(tick);
    }
  }

  const pop = document.getElementById("points-pop");
  if (pop) {
    pop.classList.add("points-pop-anim");
  }
})();
