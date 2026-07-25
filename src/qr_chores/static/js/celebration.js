(() => {
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.getElementById("confetti");
  if (!canvas || prefersReduced) return;

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

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

  const pop = document.getElementById("points-pop");
  if (pop) {
    pop.classList.add("points-pop-anim");
  }
})();
