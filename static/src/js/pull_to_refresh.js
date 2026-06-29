(function () {
    'use strict';

    let startY = 0;
    let isPulling = false;
    let pullThreshold = 70;
    let maxPull = 120;
    let ptrElement = null;
    let spinnerElement = null;

    function isScrollAtTop(target) {
        let el = target;
        while (el && el !== document.body && el !== document.documentElement) {
            const style = window.getComputedStyle(el);
            const overflowY = style.overflowY;
            if ((overflowY === 'auto' || overflowY === 'scroll') && el.scrollTop > 0) {
                return false;
            }
            el = el.parentElement;
        }
        return window.scrollY === 0;
    }

    function createPtrElement() {
        if (ptrElement) return;

        ptrElement = document.createElement('div');
        ptrElement.className = 'kser-ptr-container';
        ptrElement.innerHTML = `
            <div class="kser-ptr-card">
                <svg class="kser-ptr-spinner" viewBox="0 0 24 24">
                    <circle class="kser-ptr-track" cx="12" cy="12" r="9" fill="none" stroke="#e5e7eb" stroke-width="3"></circle>
                    <circle class="kser-ptr-head" cx="12" cy="12" r="9" fill="none" stroke="#0284c7" stroke-width="3" stroke-dasharray="56" stroke-dashoffset="56"></circle>
                    <path class="kser-ptr-arrow" d="M12 4V1L8 5l4 4V6a6 6 0 1 1-6 6h-2a8 8 0 1 0 8-8z" fill="#0284c7"></path>
                </svg>
            </div>
        `;
        document.body.appendChild(ptrElement);
        spinnerElement = ptrElement.querySelector('.kser-ptr-spinner');
    }

    function init() {
        if (!('ontouchstart' in window) && navigator.maxTouchPoints === 0) {
            return;
        }

        window.addEventListener('touchstart', function (e) {
            if (e.touches.length !== 1) return;
            const target = e.target;
            if (!isScrollAtTop(target)) return;

            startY = e.touches[0].pageY;
            isPulling = false;
        }, { passive: true });

        window.addEventListener('touchmove', function (e) {
            if (e.touches.length !== 1 || startY === 0) return;
            
            const targetY = e.touches[0].pageY;
            const diff = targetY - startY;

            if (diff > 5 && isScrollAtTop(e.target)) {
                if (!isPulling) {
                    isPulling = true;
                    createPtrElement();
                    ptrElement.classList.remove('kser-ptr-refreshing', 'kser-ptr-returning');
                    ptrElement.style.display = 'flex';
                }

                const pullDistance = Math.min(diff * 0.45, maxPull);
                ptrElement.style.transform = 'translateY(' + pullDistance + 'px)';
                
                const progress = Math.min(pullDistance / pullThreshold, 1.0);
                spinnerElement.style.transform = 'rotate(' + (progress * 360) + 'deg) scale(' + (0.3 + progress * 0.7) + ')';
                
                if (pullDistance >= pullThreshold) {
                    ptrElement.classList.add('kser-ptr-active');
                } else {
                    ptrElement.classList.remove('kser-ptr-active');
                }

                if (e.cancelable) {
                    e.preventDefault();
                }
            }
        }, { passive: false });

        window.addEventListener('touchend', function (e) {
            if (!isPulling || !ptrElement) return;

            const style = window.getComputedStyle(ptrElement);
            const matrix = new DOMMatrixReadOnly(style.transform);
            const currentPull = matrix.m42;

            if (currentPull >= pullThreshold) {
                ptrElement.classList.remove('kser-ptr-active');
                ptrElement.classList.add('kser-ptr-refreshing');
                ptrElement.style.transform = 'translateY(' + pullThreshold + 'px)';
                
                setTimeout(function () {
                    window.location.reload();
                }, 400);
            } else {
                ptrElement.classList.add('kser-ptr-returning');
                ptrElement.style.transform = 'translateY(0)';
                setTimeout(function () {
                    if (ptrElement) {
                        ptrElement.style.display = 'none';
                        isPulling = false;
                    }
                }, 300);
            }
            startY = 0;
        }, { passive: true });
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        init();
    } else {
        document.addEventListener('DOMContentLoaded', init);
    }
})();
