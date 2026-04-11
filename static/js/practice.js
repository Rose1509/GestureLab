// Practice page controller:
// - Starts/stops camera
// - Uses Mediapipe to find the hand
// - Sends cropped frames to /api/predict-sign
// - Updates prediction UI and "no hand" popup

(function () {
    const videoEl = document.getElementById('practice-camera-stream');
    const placeholder = document.getElementById('camera-placeholder');
    const startBtn = document.getElementById('start-camera-btn');
    const captureCanvas = document.getElementById('practice-capture-canvas');
    const overlayHintEl = document.getElementById('camera-overlay-hint');
    const letterEl = document.getElementById('prediction-letter');
    const confidenceEl = document.getElementById('prediction-confidence');
    const errorEl = document.getElementById('prediction-error');
    const loadingEl = document.getElementById('prediction-loading');
    const targetWrap = document.getElementById('prediction-target-wrap');
    const targetEl = document.getElementById('prediction-target');
    const targetConfWrap = document.getElementById('prediction-target-confidence-wrap');
    const targetConfEl = document.getElementById('prediction-target-confidence');
    const confidenceLabelEl = document.getElementById('prediction-confidence-label');
    const wordWrapEl = document.getElementById('prediction-word-wrap');
    const wordEl = document.getElementById('prediction-word');
    const finalWordWrapEl = document.getElementById('prediction-final-word-wrap');
    const finalWordEl = document.getElementById('prediction-final-word');
    const stopBtn = document.getElementById('stop-camera-btn');
    const retryBtn = document.getElementById('retry-camera-btn');
    const noHandModal = document.getElementById('no-hand-modal');
    const noHandCloseBtn = document.getElementById('no-hand-close-btn');
    const feedbackPanel = document.getElementById('practice-feedback-panel');
    const modelErrorPop = document.getElementById('practiceModelErrorPop');
    const modelErrorText = document.getElementById('practiceModelErrorText');
    let _modelPopTimer = null;

    function showModelErrorPop(msg) {
        if (!modelErrorPop || !modelErrorText) return;
        if (_modelPopTimer) { clearTimeout(_modelPopTimer); _modelPopTimer = null; }
        modelErrorText.textContent = msg;
        modelErrorPop.classList.add('auth-error-pop--visible');
        modelErrorPop.setAttribute('aria-hidden', 'false');
        try { modelErrorPop.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) {}
        _modelPopTimer = setTimeout(function () { hideModelErrorPop(); }, 6000);
    }
    function hideModelErrorPop() {
        if (!modelErrorPop) return;
        modelErrorPop.classList.remove('auth-error-pop--visible');
        modelErrorPop.setAttribute('aria-hidden', 'true');
    }
    const feedbackTipsList = document.getElementById('practice-feedback-tips');
    const feedbackIntroEl = document.getElementById('practice-feedback-intro');
    const demoSection = document.getElementById('practice-demo-section');
    const instructionsSection = document.getElementById('practice-instructions-section');

    let currentStream = null;
    let predictionIntervalId = null;
    let predictInFlight = false;
    let isPracticing = false;
    let bestTargetConfidence = null; // best score for the target sign this session
    let bestOverallLetter = null;    // best predicted letter this session
    let bestOverallConfidence = 0;   // best top-1 confidence this session (0–1)
    let handBox = null;              // {x,y,w,h} crop in video pixels
    let handLoopRafId = null;
    let hands = null;
    let lastHandSeenAt = null;
    let lastLandmarks = null;
    const NO_HAND_TIMEOUT_MS = 1000;

    let TARGET_LETTER = '';
    let WORD_BUILDER_ENABLED = true;

    function syncPracticePageConfig() {
        try {
            const raw = window.PRACTICE_TARGET_LETTER || '';
            if (!raw) {
                TARGET_LETTER = '';
            } else {
                const s = String(raw).trim();
                const matches = s.match(/[A-Za-z]/g);
                const ch = matches && matches.length ? matches[matches.length - 1] : null;
                TARGET_LETTER = ch ? ch.toUpperCase() : s.toUpperCase();
            }
        } catch (_) {
            TARGET_LETTER = '';
        }
        WORD_BUILDER_ENABLED = !TARGET_LETTER;
    }

    syncPracticePageConfig();

    // Word builder mode is ONLY for generic practice (no lesson target selected).
    const STABLE_FRAMES = 3;
    const MIN_LETTER_CONF = 0.45; // webcam scores are often <0.8; hiding above 0.8 hid real predictions

    let currentWord = '';
    let finalizedWord = '';
    let candidateLetter = null;
    let candidateCount = 0;
    let lastAcceptedLetter = null;
    let seenDifferentSinceAccept = true;

    function dist(a, b) {
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function resetWordBuilderUI() {
        if (!WORD_BUILDER_ENABLED) return;
        if (wordEl) wordEl.textContent = currentWord ? currentWord : '—';
        if (finalWordEl) finalWordEl.textContent = finalizedWord ? finalizedWord : '—';
    }

    function clearWordBuilder() {
        currentWord = '';
        finalizedWord = '';
        candidateLetter = null;
        candidateCount = 0;
        lastAcceptedLetter = null;
        seenDifferentSinceAccept = true;
        resetWordBuilderUI();
    }

    function finalizeCurrentWord() {
        const w = (currentWord || '').trim();
        if (!w) return;
        finalizedWord = w;
        currentWord = '';
        candidateLetter = null;
        candidateCount = 0;
        seenDifferentSinceAccept = true;
        resetWordBuilderUI();
    }

    function acceptLetter(letter) {
        if (!letter) return;
        // prevent endless repeats of same letter unless the gesture changes
        if (!seenDifferentSinceAccept && letter === lastAcceptedLetter) return;
        currentWord += letter;
        lastAcceptedLetter = letter;
        seenDifferentSinceAccept = false;
        resetWordBuilderUI();
    }

    const FEEDBACK_THRESHOLD = 0.55;

    function getLessonTips() {
        try {
            const raw = window.PRACTICE_LESSON_TIPS;
            if (Array.isArray(raw)) return raw.filter(function (s) { return String(s).trim(); });
            if (typeof raw === 'string' && raw.trim()) {
                return raw.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
            }
            return [];
        } catch (_) {
            return [];
        }
    }

    function setFeedbackPanelVisible(visible, scorePercent) {
        if (!feedbackPanel || !feedbackTipsList) return;
        if (!visible) {
            feedbackPanel.style.display = 'none';
            if (demoSection) demoSection.style.display = '';
            if (instructionsSection) instructionsSection.style.display = '';
            return;
        }
        if (demoSection) demoSection.style.display = 'none';
        if (instructionsSection) instructionsSection.style.display = 'none';
        if (feedbackIntroEl) {
            var pctText = scorePercent != null ? (Number(scorePercent).toFixed(1) + '%') : 'below 80%';
            feedbackIntroEl.textContent = 'Your score was ' + pctText + '. Follow these steps for a clearer sign:';
        }
        const tips = getLessonTips();
        feedbackTipsList.innerHTML = '';
        if (tips.length) {
            tips.forEach(function (tip) {
                const li = document.createElement('li');
                li.textContent = tip;
                feedbackTipsList.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.textContent = 'Review the demonstration image and match hand shape, orientation, and finger position.';
            feedbackTipsList.appendChild(li);
        }
        feedbackPanel.style.display = 'block';
    }

    function setPredictionPlaceholder() {
        if (letterEl) letterEl.textContent = '—';
        if (confidenceEl) confidenceEl.textContent = '';
        if (targetConfEl) targetConfEl.textContent = '';
        if (WORD_BUILDER_ENABLED) resetWordBuilderUI();
        if (errorEl) {
            errorEl.style.display = 'none';
            errorEl.textContent = '';
        }
        if (loadingEl) loadingEl.style.display = 'none';
        if (noHandModal) noHandModal.style.display = 'none';
    }

    function setAnalyzing(isAnalyzing) {
        if (!loadingEl) return;
        loadingEl.style.display = isAnalyzing ? 'flex' : 'none';
        const showBlocks = !isAnalyzing;

        if (targetWrap) {
            // Keep target letter visible as a reminder
            targetWrap.style.display = TARGET_LETTER ? 'block' : 'none';
        }
        const letterWrap = letterEl ? letterEl.parentElement : null;
        const confWrap = confidenceLabelEl ? confidenceLabelEl.parentElement : null;
        if (letterWrap) letterWrap.style.display = showBlocks ? 'block' : 'none';
        if (confWrap) confWrap.style.display = showBlocks ? 'block' : 'none';
        if (TARGET_LETTER && targetConfWrap) {
            // Final prediction appears only after analyzing + stop
            targetConfWrap.style.display = showBlocks && !isPracticing ? 'block' : 'none';
        }
    }

    function setPredictionVisible(visible) {
        const show = !!visible;
        if (confidenceEl) confidenceEl.textContent = show ? '—%' : '';
        if (confidenceLabelEl) confidenceLabelEl.style.display = show ? 'block' : 'none';
        const confWrap = confidenceLabelEl ? confidenceLabelEl.parentElement : null;
        if (confWrap) confWrap.style.display = show ? 'block' : 'none';

        if (TARGET_LETTER && targetConfWrap) {
            const shouldShowFinal = show && !isPracticing;
            targetConfWrap.style.display = shouldShowFinal ? 'block' : 'none';
            if (targetConfEl && shouldShowFinal && bestTargetConfidence == null) {
                targetConfEl.textContent = '—%';
            }
        }
        if (loadingEl && !show) loadingEl.style.display = 'none';
    }

    function stopHandTrackingLoop() {
        if (handLoopRafId) {
            cancelAnimationFrame(handLoopRafId);
            handLoopRafId = null;
        }
        handBox = null;
        if (overlayHintEl) {
            overlayHintEl.style.display = 'none';
            overlayHintEl.textContent = '';
        }
    }

    function setOverlayHint(text) {
        if (!overlayHintEl) return;
        if (!text) {
            overlayHintEl.style.display = 'none';
            overlayHintEl.textContent = '';
            return;
        }
        overlayHintEl.textContent = text;
        overlayHintEl.style.display = 'block';
    }

    function updatePositionHint() {
        if (!isPracticing || !videoEl || !videoEl.videoWidth || !videoEl.videoHeight) return;
        if (!handBox) {
            setOverlayHint('Please show your hand clearly inside the camera view');
            return;
        }
        const vw = videoEl.videoWidth;
        const vh = videoEl.videoHeight;
        const cx = handBox.x + handBox.w / 2;
        const cy = handBox.y + handBox.h / 2;

        const leftBound = vw * 0.40;
        const rightBound = vw * 0.60;
        const topBound = vh * 0.40;
        const bottomBound = vh * 0.60;

        const area = handBox.w * handBox.h;
        const frameArea = vw * vh;
        const areaRatio = frameArea > 0 ? area / frameArea : 0;

        const hints = [];
        if (cx < leftBound) hints.push('Move right');
        else if (cx > rightBound) hints.push('Move left');
        if (cy < topBound) hints.push('Move down');
        else if (cy > bottomBound) hints.push('Move up');
        if (areaRatio > 0 && areaRatio < 0.06) hints.push('Move closer');
        else if (areaRatio > 0.30) hints.push('Move farther');

        setOverlayHint(hints.length ? hints.join(' • ') : 'Good position');
    }

    function ensureHands() {
        if (hands) return hands;
        if (!window.Hands) return null;
        hands = new window.Hands({
            locateFile: function (file) {
                return 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/' + file;
            }
        });
        hands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5
        });
        hands.onResults(function (results) {
            const lm = results && results.multiHandLandmarks && results.multiHandLandmarks[0];
            if (!lm || !videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
                handBox = null;
                lastLandmarks = null;
                return;
            }
            lastLandmarks = lm;
            let minX = 1, minY = 1, maxX = 0, maxY = 0;
            for (var i = 0; i < lm.length; i++) {
                const p = lm[i];
                if (p.x < minX) minX = p.x;
                if (p.y < minY) minY = p.y;
                if (p.x > maxX) maxX = p.x;
                if (p.y > maxY) maxY = p.y;
            }
            // Slightly more context around the hand (notebook trains on full letter crops)
            const pad = 0.2;
            minX = Math.max(0, minX - pad);
            minY = Math.max(0, minY - pad);
            maxX = Math.min(1, maxX + pad);
            maxY = Math.min(1, maxY + pad);

            const vw = videoEl.videoWidth;
            const vh = videoEl.videoHeight;
            let x = Math.floor(minX * vw);
            let y = Math.floor(minY * vh);
            let w = Math.ceil((maxX - minX) * vw);
            let h = Math.ceil((maxY - minY) * vh);

            const size = Math.max(w, h);
            const cx = x + w / 2;
            const cy = y + h / 2;
            x = Math.floor(cx - size / 2);
            y = Math.floor(cy - size / 2);
            w = size;
            h = size;

            if (x < 0) x = 0;
            if (y < 0) y = 0;
            if (x + w > vw) x = vw - w;
            if (y + h > vh) y = vh - h;
            if (w <= 0 || h <= 0) {
                handBox = null;
                updatePositionHint();
                return;
            }
            handBox = { x: x, y: y, w: w, h: h };
            lastHandSeenAt = Date.now();
            if (noHandModal) noHandModal.style.display = 'none';
            updatePositionHint();
        });
        return hands;
    }

    function startHandTrackingLoop() {
        stopHandTrackingLoop();
        const handsApi = ensureHands();
        if (!handsApi) {
            handBox = null;
            return;
        }
        let sending = false;
        async function tick() {
            handLoopRafId = requestAnimationFrame(tick);
            if (!videoEl || !videoEl.srcObject || videoEl.readyState < 2) return;
            if (sending) return;
            sending = true;
            try {
                await handsApi.send({ image: videoEl });
            } catch (_) {
                // ignore
            } finally {
                sending = false;
            }
            if (isPracticing) {
                const now = Date.now();
                const tooLong = !lastHandSeenAt || (now - lastHandSeenAt) >= NO_HAND_TIMEOUT_MS;
                if (tooLong && noHandModal) noHandModal.style.display = 'flex';
            }
        }
        tick();
    }

    function captureFrameToCanvas() {
        if (!videoEl.srcObject || videoEl.readyState < 2) return false;
        const w = captureCanvas.width;
        const h = captureCanvas.height;
        const ctx = captureCanvas.getContext('2d');
        const vw = videoEl.videoWidth || w;
        const vh = videoEl.videoHeight || h;
        let sx, sy, sw, sh;
        if (handBox) {
            sx = handBox.x; sy = handBox.y; sw = handBox.w; sh = handBox.h;
        } else {
            const size = Math.min(vw, vh);
            sx = Math.floor((vw - size) / 2);
            sy = Math.floor((vh - size) / 2);
            sw = size;
            sh = size;
        }
        ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, w, h);
        return true;
    }

    function captureAndPredict() {
        if (predictInFlight || !captureCanvas) return;
        const ok = captureFrameToCanvas();
        if (!ok) return;
        captureCanvas.toBlob(function (blob) {
            if (!blob) return;
            const form = new FormData();
            form.append('frame', blob, 'frame.jpg');
            if (TARGET_LETTER) form.append('target', TARGET_LETTER);
            predictInFlight = true;
            fetch('/api/predict-sign', { method: 'POST', body: form })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.error) {
                        letterEl.textContent = '—';
                        confidenceEl.textContent = '—%';
                        if (targetConfEl) targetConfEl.textContent = '—%';
                        if (errorEl) {
                            errorEl.textContent = data.error;
                            errorEl.style.display = 'block';
                        }
                        showModelErrorPop(data.error);
                        return;
                    }
                    if (errorEl) {
                        errorEl.style.display = 'none';
                        errorEl.textContent = '';
                    }
                    letterEl.textContent = data.letter != null ? String(data.letter) : '—';
                    const pct = data.confidence != null ? (data.confidence * 100).toFixed(1) : '0';
                    confidenceEl.textContent = pct + '%';

                    // Word builder logic (ONLY when no lesson selected)
                    if (WORD_BUILDER_ENABLED) {
                        const topLetter = data.letter != null ? String(data.letter) : null;
                        const topConf = (typeof data.confidence === 'number') ? data.confidence : 0;

                        // Only show letter when confidence passes threshold
                        if (!topLetter || topConf < MIN_LETTER_CONF) {
                            if (letterEl) letterEl.textContent = '—';
                        }

                        // Mark "gesture changed" whenever top letter differs or confidence drops
                        if (!topLetter || topConf < MIN_LETTER_CONF || (lastAcceptedLetter && topLetter !== lastAcceptedLetter)) {
                            seenDifferentSinceAccept = true;
                        }

                        if (topLetter && topConf >= MIN_LETTER_CONF) {
                            // stability gate
                            if (candidateLetter === topLetter) {
                                candidateCount += 1;
                            } else {
                                candidateLetter = topLetter;
                                candidateCount = 1;
                            }
                            if (candidateCount >= STABLE_FRAMES) {
                                acceptLetter(topLetter);
                                candidateCount = 0;
                            }
                        } else {
                            candidateLetter = null;
                            candidateCount = 0;
                        }
                    }
                    if (data.letter != null && typeof data.confidence === 'number') {
                        if (data.confidence > bestOverallConfidence) {
                            bestOverallConfidence = data.confidence;
                            bestOverallLetter = String(data.letter);
                        }
                    }
                    if (TARGET_LETTER) {
                        const t = data.target_confidence;
                        if (typeof t === 'number') {
                            if (bestTargetConfidence == null || t > bestTargetConfidence) {
                                bestTargetConfidence = t;
                            }
                        }
                    }
                })
                .catch(function () {
                    letterEl.textContent = '—';
                    confidenceEl.textContent = '—%';
                    if (errorEl) {
                        errorEl.textContent = 'Network error. Is the server running?';
                        errorEl.style.display = 'block';
                    }
                    showModelErrorPop('Network error. Is the server running?');
                })
                .finally(function () {
                    predictInFlight = false;
                });
        }, 'image/jpeg', 0.92);
    }

    function captureAndPredictOnce() {
        return new Promise(function (resolve) {
            if (predictInFlight) return resolve(null);
            const ok = captureFrameToCanvas();
            if (!ok) return resolve(null);
            captureCanvas.toBlob(function (blob) {
                if (!blob) return resolve(null);
                const form = new FormData();
                form.append('frame', blob, 'frame.jpg');
                if (TARGET_LETTER) form.append('target', TARGET_LETTER);
                predictInFlight = true;
                fetch('/api/predict-sign', { method: 'POST', body: form })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data || data.error) {
                            letterEl.textContent = '—';
                            confidenceEl.textContent = '—%';
                            if (targetConfEl) targetConfEl.textContent = '—%';
                            if (errorEl && data && data.error) {
                                errorEl.textContent = data.error;
                                errorEl.style.display = 'block';
                            }
                            if (data && data.error) showModelErrorPop(data.error);
                            resolve(data || null);
                            return;
                        }
                        if (errorEl) {
                            errorEl.style.display = 'none';
                            errorEl.textContent = '';
                        }
                        letterEl.textContent = data.letter != null ? String(data.letter) : '—';
                        const pct = data.confidence != null ? (data.confidence * 100).toFixed(1) : '0';
                        confidenceEl.textContent = pct + '%';
                        if (data.letter != null && typeof data.confidence === 'number') {
                            if (data.confidence > bestOverallConfidence) {
                                bestOverallConfidence = data.confidence;
                                bestOverallLetter = String(data.letter);
                            }
                        }
                        if (TARGET_LETTER) {
                            const t = data.target_confidence;
                            if (typeof t === 'number') {
                                if (bestTargetConfidence == null || t > bestTargetConfidence) {
                                    bestTargetConfidence = t;
                                }
                            }
                        }
                        resolve(data);
                    })
                    .catch(function () {
                        letterEl.textContent = '—';
                        confidenceEl.textContent = '—%';
                        if (targetConfEl) targetConfEl.textContent = '—%';
                        if (errorEl) {
                            errorEl.textContent = 'Network error. Is the server running?';
                            errorEl.style.display = 'block';
                        }
                        showModelErrorPop('Network error. Is the server running?');
                        resolve(null);
                    })
                    .finally(function () {
                        predictInFlight = false;
                    });
            }, 'image/jpeg', 0.92);
        });
    }

    function startPredictionLoop() {
        stopPredictionLoop();
        if (!videoEl || !videoEl.srcObject || !captureCanvas || !letterEl || !confidenceEl) return;

        if (TARGET_LETTER && targetWrap && targetEl && targetConfWrap && targetConfEl) {
            targetWrap.style.display = 'block';
            targetEl.textContent = TARGET_LETTER;
            if (confidenceLabelEl) confidenceLabelEl.textContent = 'Top prediction';
        } else {
            if (targetWrap) targetWrap.style.display = 'none';
            if (confidenceLabelEl) confidenceLabelEl.textContent = 'Confidence';
        }
        setPredictionVisible(true);
        captureAndPredict();
        predictionIntervalId = setInterval(captureAndPredict, 350);
        startPredictionLoop._captureAndPredictOnce = captureAndPredictOnce;
    }

    function stopPredictionLoop() {
        if (predictionIntervalId) {
            clearInterval(predictionIntervalId);
            predictionIntervalId = null;
        }
        stopHandTrackingLoop();
    }

    function getCameraErrorMessage(err) {
        const name = err && err.name ? err.name : '';
        if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
            return 'Camera access was blocked. Allow the camera for this site in your browser address bar or site settings, then try again.';
        }
        if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
            return 'No camera was found. Connect a webcam and try again.';
        }
        if (name === 'NotReadableError' || name === 'TrackStartError') {
            return 'Your camera may be in use by another app. Close other programs using the camera and try again.';
        }
        if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
            return 'Could not start the camera with the required settings. Try another browser or device.';
        }
        if (err && err.message && typeof err.message === 'string' && err.message.indexOf('not supported') !== -1) {
            return err.message;
        }
        return 'Could not access the camera. Check permissions and try again.';
    }

    async function isCameraPermissionGranted() {
        try {
            if (!navigator.permissions || typeof navigator.permissions.query !== 'function') {
                return false;
            }
            const st = await navigator.permissions.query({ name: 'camera' });
            return st && st.state === 'granted';
        } catch (_) {
            return false;
        }
    }

    function openCameraPermissionModal() {
        const modal = document.getElementById('camera-permission-modal');
        const errEl = document.getElementById('camera-permission-error');
        const allow = document.getElementById('camera-permission-allow');
        if (!modal) {
            startCamera().catch(function () {});
            return;
        }
        if (errEl) {
            errEl.style.display = 'none';
            errEl.textContent = '';
        }
        if (allow) {
            allow.disabled = false;
            allow.textContent = 'Allow camera';
        }
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        setTimeout(function () {
            if (allow) allow.focus();
        }, 30);
    }

    function closeCameraPermissionModal() {
        const modal = document.getElementById('camera-permission-modal');
        const allow = document.getElementById('camera-permission-allow');
        if (modal) modal.style.display = 'none';
        document.body.style.overflow = '';
        if (allow) {
            allow.disabled = false;
            allow.textContent = 'Allow camera';
        }
    }

    async function onAllowCameraFromModal() {
        const allow = document.getElementById('camera-permission-allow');
        const errEl = document.getElementById('camera-permission-error');
        if (allow) {
            allow.disabled = true;
            allow.textContent = 'Waiting for browser…';
        }
        if (errEl) {
            errEl.style.display = 'none';
            errEl.textContent = '';
        }
        try {
            await startCamera();
            closeCameraPermissionModal();
        } catch (err) {
            console.error('Error accessing camera:', err);
            if (errEl) {
                errEl.textContent = getCameraErrorMessage(err);
                errEl.style.display = 'block';
            }
            if (allow) {
                allow.disabled = false;
                allow.textContent = 'Try again';
            }
        }
    }

    async function onStartPracticeClick() {
        if (startBtn && startBtn.disabled) return;
        try {
            if (await isCameraPermissionGranted()) {
                try {
                    await startCamera();
                } catch (err) {
                    console.error(err);
                    openCameraPermissionModal();
                    const errEl = document.getElementById('camera-permission-error');
                    const allow = document.getElementById('camera-permission-allow');
                    if (errEl) {
                        errEl.textContent = getCameraErrorMessage(err);
                        errEl.style.display = 'block';
                    }
                    if (allow) {
                        allow.disabled = false;
                        allow.textContent = 'Try again';
                    }
                }
                return;
            }
        } catch (_) {
            /* fall through to modal */
        }
        openCameraPermissionModal();
    }

    async function startCamera() {
        if (!videoEl || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Camera is not supported in this browser.');
        }
        try {
            if (currentStream) {
                currentStream.getTracks().forEach(function (t) { t.stop(); });
                currentStream = null;
            }
            await stopPractice(false);
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user' },
                audio: false
            });
            currentStream = stream;
            videoEl.srcObject = stream;
            videoEl.style.display = 'block';
            if (placeholder) placeholder.style.display = 'none';
            const playPromise = videoEl.play && videoEl.play();
            if (playPromise && typeof playPromise.then === 'function') {
                playPromise.then(function () { startPractice(); }).catch(function () {
                    startPractice();
                });
            } else {
                startPractice();
            }
        } catch (err) {
            console.error('Error accessing camera:', err);
            if (placeholder) placeholder.style.display = 'block';
            setPredictionPlaceholder();
            throw err;
        }
    }

    function startPractice() {
        if (isPracticing) return;
        isPracticing = true;
        bestTargetConfidence = null;
        bestOverallLetter = null;
        bestOverallConfidence = 0;
        lastHandSeenAt = null;
        if (WORD_BUILDER_ENABLED) clearWordBuilder();
        if (feedbackPanel) feedbackPanel.style.display = 'none';
        if (demoSection) demoSection.style.display = '';
        if (instructionsSection) instructionsSection.style.display = '';
        setPredictionPlaceholder();
        setPredictionVisible(true);
        setAnalyzing(false);
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';
        if (retryBtn) retryBtn.style.display = 'inline-flex';
        setOverlayHint('Please show your hand clearly inside the camera view');
        startHandTrackingLoop();
        startPredictionLoop();
    }

    async function stopPractice(showFinalScore) {
        isPracticing = false;
        setOverlayHint('');
        if (noHandModal) noHandModal.style.display = 'none';

        if (showFinalScore && typeof startPredictionLoop._captureAndPredictOnce === 'function') {
            try {
                setAnalyzing(true);
                await startPredictionLoop._captureAndPredictOnce();
                if (bestOverallLetter != null) {
                    letterEl.textContent = bestOverallLetter;
                    const finalTopPct = (bestOverallConfidence * 100).toFixed(1);
                    confidenceEl.textContent = finalTopPct + '%';
                }
                setTimeout(function () {
                    setAnalyzing(false);
                }, 4500);
            } catch (_) {}
        }

        stopPredictionLoop();
        if (showFinalScore) {
            setPredictionVisible(true);
        } else {
            setPredictionVisible(false);
        }

        if (currentStream) {
            currentStream.getTracks().forEach(function (t) { t.stop(); });
            currentStream = null;
        }
        if (videoEl) {
            videoEl.srcObject = null;
            videoEl.style.display = 'none';
        }
        if (placeholder) placeholder.style.display = 'block';

        if (startBtn) startBtn.style.display = 'inline-flex';
        if (stopBtn) stopBtn.style.display = 'none';
        if (retryBtn) retryBtn.style.display = 'inline-flex';

        if (showFinalScore && TARGET_LETTER && targetWrap && targetEl && targetConfWrap && targetConfEl) {
            targetWrap.style.display = 'block';
            targetEl.textContent = TARGET_LETTER;
            targetConfWrap.style.display = 'block';
            if (bestTargetConfidence == null) {
                targetConfEl.textContent = '—%';
            } else {
                const finalPct = (bestTargetConfidence * 100).toFixed(1);
                targetConfEl.textContent = finalPct + '%';
            }
            if (feedbackPanel) {
                if (bestTargetConfidence != null && bestTargetConfidence < FEEDBACK_THRESHOLD) {
                    setFeedbackPanelVisible(true, bestTargetConfidence * 100);
                } else {
                    setFeedbackPanelVisible(false);
                }
            }
        } else if (feedbackPanel) {
            setFeedbackPanelVisible(false);
        }
    }

    async function initPracticePage() {
        syncPracticePageConfig();
        try {
            const r = await fetch('/api/practice-status');
            const d = await r.json();
            if (d.ready !== true) {
                const errMsg = d.message ||
                    'Model files not found. Add sign_language_model_improved.keras and class_labels.pkl to the models folder, then restart the server.';
                const banner = document.getElementById('practice-ai-banner');
                if (banner) {
                    banner.style.display = 'block';
                    banner.textContent = errMsg;
                }
                showModelErrorPop(errMsg);
                const sb = document.getElementById('start-camera-btn');
                if (sb) {
                    sb.disabled = true;
                    sb.setAttribute('aria-disabled', 'true');
                    sb.style.opacity = '0.65';
                    sb.style.cursor = 'not-allowed';
                }
            }
        } catch (_) {
            /* Status check failed; user can still try Start (e.g. offline docs) */
        }
        // Only show word UI on generic practice page (no lesson selected)
        if (WORD_BUILDER_ENABLED) {
            if (wordWrapEl) wordWrapEl.style.display = 'block';
            if (finalWordWrapEl) finalWordWrapEl.style.display = 'block';
            if (retryBtn) retryBtn.textContent = 'Retake';
        } else {
            if (wordWrapEl) wordWrapEl.style.display = 'none';
            if (finalWordWrapEl) finalWordWrapEl.style.display = 'none';
            if (retryBtn) retryBtn.textContent = 'Retry';
        }
        if (startBtn) {
            startBtn.addEventListener('click', onStartPracticeClick);
        }
        if (stopBtn) {
            stopBtn.addEventListener('click', function () {
                if (WORD_BUILDER_ENABLED && isPracticing) {
                    finalizeCurrentWord();
                    stopPractice(false);
                    return;
                }
                stopPractice(true);
            });
        }
        if (retryBtn) {
            retryBtn.addEventListener('click', function () {
                if (WORD_BUILDER_ENABLED && isPracticing) {
                    clearWordBuilder();
                    return;
                }
                onStartPracticeClick();
            });
        }
        var permModal = document.getElementById('camera-permission-modal');
        var permCancel = document.getElementById('camera-permission-cancel');
        var permAllow = document.getElementById('camera-permission-allow');
        if (permCancel) {
            permCancel.addEventListener('click', closeCameraPermissionModal);
        }
        if (permAllow) {
            permAllow.addEventListener('click', onAllowCameraFromModal);
        }
        if (permModal) {
            permModal.addEventListener('click', function (e) {
                if (e.target === permModal) {
                    closeCameraPermissionModal();
                }
            });
        }
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            if (!permModal || permModal.style.display !== 'flex') return;
            closeCameraPermissionModal();
        });
        if (noHandCloseBtn && noHandModal) {
            noHandCloseBtn.addEventListener('click', function () {
                noHandModal.style.display = 'none';
            });
        }
        window.addEventListener('beforeunload', function () {
            stopPractice(false);
        });
        setPredictionPlaceholder();
        setPredictionVisible(false);
        if (TARGET_LETTER && targetWrap && targetEl) {
            targetWrap.style.display = 'block';
            targetEl.textContent = TARGET_LETTER;
        }
    }

    document.addEventListener('DOMContentLoaded', initPracticePage);
})();

