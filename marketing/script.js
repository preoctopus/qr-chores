/**
 * QR Chores - Marketing Landing Page Interactive Script
 */

document.addEventListener('DOMContentLoaded', () => {
  initPricingToggle();
  initFaqAccordion();
  initSimulator();
  initModals();
  initMobileNav();
});

/* ==========================================================================
   1. Pricing Toggle (Monthly vs Annual)
   ========================================================================== */
function initPricingToggle() {
  const toggleWrapper = document.getElementById('pricing-toggle-wrapper');
  const toggleSwitch = document.getElementById('pricing-toggle');
  const priceStarter = document.getElementById('price-starter');
  const pricePro = document.getElementById('price-pro');
  const billingCycleLabels = document.querySelectorAll('.billing-cycle');

  if (!toggleSwitch) return;

  toggleSwitch.addEventListener('click', () => {
    toggleWrapper.classList.toggle('annual');
    const isAnnual = toggleWrapper.classList.contains('annual');

    if (isAnnual) {
      priceStarter.innerHTML = '$0 <span>/ year</span>';
      pricePro.innerHTML = '$4.99 <span>/ month ($59 billed annually)</span>';
      billingCycleLabels.forEach(el => el.textContent = 'billed annually');
    } else {
      priceStarter.innerHTML = '$0 <span>/ forever</span>';
      pricePro.innerHTML = '$6.99 <span>/ month</span>';
      billingCycleLabels.forEach(el => el.textContent = 'billed monthly');
    }
  });
}

/* ==========================================================================
   2. FAQ Accordion
   ========================================================================== */
function initFaqAccordion() {
  const faqItems = document.querySelectorAll('.faq-item');

  faqItems.forEach(item => {
    const questionBtn = item.querySelector('.faq-question');
    questionBtn.addEventListener('click', () => {
      const isActive = item.classList.contains('active');

      // Close all active items
      faqItems.forEach(i => i.classList.remove('active'));

      // Toggle current
      if (!isActive) {
        item.classList.contains('active') ? item.classList.remove('active') : item.classList.add('active');
      }
    });
  });
}

/* ==========================================================================
   3. Interactive QR Chore Simulator
   ========================================================================== */
function initSimulator() {
  const choreSelect = document.getElementById('sim-chore-select');
  const scanBtn = document.getElementById('sim-scan-btn');
  const photoBtn = document.getElementById('sim-photo-btn');
  const submitBtn = document.getElementById('sim-submit-btn');
  const resetBtn = document.getElementById('sim-reset-btn');

  const simBox = document.getElementById('sim-box-content');
  const simPhoto = document.getElementById('sim-photo-img');
  const simReward = document.getElementById('sim-reward-display');
  const simStepIndicator = document.getElementById('sim-step-indicator');
  const simPointsDisplay = document.getElementById('sim-points-val');

  if (!scanBtn) return;

  let currentStep = 1;
  let photoAttached = false;

  const choreData = {
    dish: { title: 'Dishwasher Duty', points: 150, bonus: 50, photo: 'Required' },
    dog: { title: 'Feed & Walk Dog', points: 100, bonus: 25, photo: 'Optional' },
    room: { title: 'Clean & Vacuum Room', points: 200, bonus: 75, photo: 'Required' }
  };

  // Scan QR Step
  scanBtn.addEventListener('click', () => {
    scanBtn.disabled = true;
    scanBtn.textContent = '⚡ Scanning QR...';
    simBox.innerHTML = `
      <div style="display:flex; flex-direction:column; align-items:center; gap:12px;">
        <div style="width:60px; height:60px; border:3px solid var(--accent-purple); border-top-color:transparent; border-radius:50%; animation:spin 0.8s linear infinite;"></div>
        <p style="font-weight:600; color:var(--accent-cyan);">Reading permanent QR token...</p>
      </div>
      <style>@keyframes spin { 100% { transform: rotate(360deg); } }</style>
    `;

    setTimeout(() => {
      currentStep = 2;
      simStepIndicator.textContent = 'STEP 2: CONFIRM CHORE & ATTACH PHOTO';
      const selected = choreSelect.value;
      const data = choreData[selected];

      simBox.innerHTML = `
        <div style="text-align:left; width:100%;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:700; font-size:1.1rem; color:white;">${data.title}</span>
            <span style="font-size:0.8rem; background:rgba(16,185,129,0.2); color:#34d399; padding:4px 10px; border-radius:12px;">ON TIME</span>
          </div>
          <p style="font-size:0.9rem; color:var(--text-muted);">Photo Policy: <strong>${data.photo}</strong></p>
          <p style="font-size:0.9rem; color:var(--accent-amber);">Base Award: +${data.points} pts (Early Bonus: +${data.bonus} pts)</p>
        </div>
      `;

      scanBtn.style.display = 'none';
      photoBtn.style.display = 'inline-flex';
      submitBtn.style.display = 'inline-flex';
    }, 1200);
  });

  // Attach Photo Step
  photoBtn.addEventListener('click', () => {
    photoAttached = true;
    simPhoto.src = 'assets/appicon-new-dark.jpg';
    simPhoto.style.display = 'block';
    photoBtn.textContent = '✅ Photo Proof Attached';
    photoBtn.style.background = 'rgba(16, 185, 129, 0.2)';
    photoBtn.style.borderColor = 'var(--accent-green)';
  });

  // Complete Chore Step
  submitBtn.addEventListener('click', () => {
    const selected = choreSelect.value;
    const data = choreData[selected];
    const totalPoints = data.points + data.bonus;

    simStepIndicator.textContent = 'STEP 3: CELEBRATION & POINTS LEDGER RECORDED';
    simBox.style.display = 'none';
    simPhoto.style.display = 'none';

    simReward.style.display = 'flex';
    simPointsDisplay.textContent = `+${totalPoints} PTS!`;

    submitBtn.style.display = 'none';
    photoBtn.style.display = 'none';
    resetBtn.style.display = 'inline-flex';
  });

  // Reset Simulator
  resetBtn.addEventListener('click', () => {
    currentStep = 1;
    photoAttached = false;

    simStepIndicator.textContent = 'STEP 1: TAP TO SIMULATE QR SCAN';
    simBox.style.display = 'flex';
    simBox.innerHTML = `
      <div style="text-align:center;">
        <div style="font-size:3rem; margin-bottom:10px;">📱</div>
        <p style="color:var(--text-muted);">Ready to scan permanent sticker code</p>
      </div>
    `;

    simReward.style.display = 'none';
    simPhoto.style.display = 'none';

    scanBtn.disabled = false;
    scanBtn.textContent = '📷 Scan Chore QR Code';
    scanBtn.style.display = 'inline-flex';

    photoBtn.textContent = '📸 Attach Photo Proof';
    photoBtn.style.background = 'var(--bg-glass)';
    photoBtn.style.borderColor = 'var(--border-color)';
    photoBtn.style.display = 'none';

    submitBtn.style.display = 'none';
    resetBtn.style.display = 'none';
  });
}

/* ==========================================================================
   4. Modal Dialogs (Sign-up / Free Trial)
   ========================================================================== */
function initModals() {
  const modalOverlay = document.getElementById('signup-modal');
  const openButtons = document.querySelectorAll('.open-signup-modal');
  const closeBtn = document.getElementById('modal-close-btn');
  const signupForm = document.getElementById('signup-form');

  if (!modalOverlay) return;

  openButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      modalOverlay.classList.add('open');
    });
  });

  closeBtn.addEventListener('click', () => {
    modalOverlay.classList.remove('open');
  });

  modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) {
      modalOverlay.classList.remove('open');
    }
  });

  if (signupForm) {
    signupForm.addEventListener('submit', (e) => {
      e.preventDefault();
      signupForm.innerHTML = `
        <div style="text-align:center; padding: 20px 0;">
          <div style="font-size:3.5rem; margin-bottom:16px;">🎉</div>
          <h3 style="font-size:1.5rem; margin-bottom:12px; color:var(--accent-green);">Trial Activated!</h3>
          <p style="color:var(--text-muted); font-size:0.95rem; margin-bottom:24px;">Welcome to QR Chores. Check your email for parent dashboard login details and printable sticker sheets!</p>
          <button class="btn btn-primary" onclick="document.getElementById('signup-modal').classList.remove('open')">Go to Dashboard Demo</button>
        </div>
      `;
    });
  }
}

/* ==========================================================================
   5. Mobile Navigation
   ========================================================================== */
function initMobileNav() {
  const mobileToggle = document.getElementById('mobile-toggle');
  const navLinks = document.getElementById('nav-links');

  if (!mobileToggle || !navLinks) return;

  mobileToggle.addEventListener('click', () => {
    const isOpen = navLinks.style.display === 'flex';
    if (isOpen) {
      navLinks.style.display = 'none';
    } else {
      navLinks.style.display = 'flex';
      navLinks.style.flexDirection = 'column';
      navLinks.style.position = 'absolute';
      navLinks.style.top = '80px';
      navLinks.style.left = '0';
      navLinks.style.width = '100%';
      navLinks.style.background = 'rgba(9, 13, 22, 0.95)';
      navLinks.style.backdropFilter = 'blur(16px)';
      navLinks.style.padding = '24px';
      navLinks.style.borderBottom = '1px solid var(--border-color)';
    }
  });
}
