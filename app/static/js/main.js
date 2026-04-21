// جلوگیری از اضافه شدن چندباره ایونت
if (!window.__cartListenerAttached) {
  window.__cartListenerAttached = true;

  document.addEventListener("click", function (e) {
    // =========================
    // REMOVE ITEM (CART)
    // =========================
    const removeBtn = e.target.closest(".remove-item-btn");
    if (removeBtn) {
      e.preventDefault();

      const itemId = removeBtn.dataset.id;
      const csrf = removeBtn.dataset.csrf;

      fetch(`/cart/remove/${itemId}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          const row = removeBtn.closest("tr");
          if (row) row.remove();

          document.getElementById("cart-count").innerText = data.cart_count;
          document.getElementById("cart-total").innerText = data.cart_total;

          checkCartEmpty();
        });

      return;
    }

    // =========================
    // ADD TO CART
    // =========================
    const cartBtn = e.target.closest(".add-to-cart-btn");
    if (cartBtn) {
      e.preventDefault();

      // prevent multiple rapid clicks
      if (cartBtn.dataset.loading === "true") return;
      cartBtn.dataset.loading = "true";

      const slug = cartBtn.dataset.slug;
      const csrf = cartBtn.dataset.csrf;

      fetch(`/cart/add/${slug}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          // ✅ CART COUNT (single source of truth)
          const cartCountEl = document.getElementById("cart-count");
          if (
            cartCountEl &&
            data.cart_count !== undefined &&
            cartCountEl.innerText != data.cart_count
          ) {
            cartCountEl.innerText = data.cart_count;
          }

          // =========================
          // UI STATE FLOW
          // =========================

          // STEP 1: immediate feedback
          if (data.already_in_cart) {
            cartBtn.innerText = "Already in Cart";
          } else {
            cartBtn.innerText = "Added ✓";
          }

          cartBtn.disabled = true;
          cartBtn.classList.remove("btn-success");
          cartBtn.classList.add("btn-success");

          // STEP 2: transition to "View Cart"
          setTimeout(() => {
            cartBtn.innerText = "View Cart";

            // make it clickable to cart page
            cartBtn.disabled = false;
            cartBtn.onclick = () => {
              window.location.href = "/cart";
            };
          }, 600); // short UX delay
        })
        .finally(() => {
          cartBtn.dataset.loading = "false";
        });

      return;
    }

    // =========================
    // INCREASE
    // =========================
    const incBtn = e.target.closest(".increase-btn");
    if (incBtn) {
      e.preventDefault();

      const itemId = incBtn.dataset.id;
      const csrf = incBtn.dataset.csrf;

      fetch(`/cart/increase/${itemId}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          document.getElementById(`qty-${itemId}`).innerText = data.quantity;
          document.getElementById(`subtotal-${itemId}`).innerText =
            data.subtotal;
          document.getElementById("cart-total").innerText = data.cart_total;
        });

      return;
    }

    // =========================
    // DECREASE
    // =========================
    const decBtn = e.target.closest(".decrease-btn");
    if (decBtn) {
      e.preventDefault();

      const itemId = decBtn.dataset.id;
      const csrf = decBtn.dataset.csrf;

      fetch(`/cart/decrease/${itemId}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          if (data.deleted) {
            const row = decBtn.closest("tr");
            if (row) row.remove();
          } else {
            document.getElementById(`qty-${itemId}`).innerText = data.quantity;
            document.getElementById(`subtotal-${itemId}`).innerText =
              data.subtotal;
          }

          document.getElementById("cart-total").innerText = data.cart_total;

          checkCartEmpty();
        });

      return;
    }

    // =========================
    // ADD TO WISHLIST
    // =========================
    const wishlistBtn = e.target.closest(".add-to-wishlist-btn");
    if (wishlistBtn) {
      e.preventDefault();

      const slug = wishlistBtn.dataset.slug;
      const csrf = wishlistBtn.dataset.csrf;

      fetch(`/wishlist/add/${slug}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          const wishCountEl = document.getElementById("wishlist-count");
          if (wishCountEl && data.wishlist_count !== undefined) {
            wishCountEl.innerText = data.wishlist_count;
          }

          if (data.action === "added") {
            wishlistBtn.classList.remove("btn-outline-danger");
            wishlistBtn.classList.add("btn-danger");
          } else {
            wishlistBtn.classList.remove("btn-danger");
            wishlistBtn.classList.add("btn-outline-danger");
          }
        });

      return;
    }

    // =========================
    // REMOVE FROM WISHLIST
    // =========================
    const removeWishBtn = e.target.closest(".remove-from-wishlist-btn");
    if (removeWishBtn) {
      e.preventDefault();

      const slug = removeWishBtn.dataset.slug;
      const csrf = removeWishBtn.dataset.csrf;

      fetch(`/wishlist/remove/${slug}`, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then((data) => {
          if (!data.success) return;

          document.getElementById("wishlist-count").innerText =
            data.wishlist_count;

          const card = removeWishBtn.closest(".wishlist-card, .card, tr");
          if (card) card.remove();
        });

      return;
    }
  });
}

// =========================
// CART EMPTY CHECK
// =========================
function checkCartEmpty() {
  const rows = document.querySelectorAll("tbody tr");
  const summary = document.getElementById("cart-summary");
  const empty = document.getElementById("empty-cart");

  if (rows.length === 0) {
    if (summary) summary.style.display = "none";
    if (empty) empty.classList.remove("d-none");
  } else {
    if (summary) summary.style.display = "block";
    if (empty) empty.classList.add("d-none");
  }
}

// =========================
// LIVE SEARCH
// =========================
const searchInput = document.getElementById("searchInput");
const resultsBox = document.getElementById("searchResults");

if (searchInput && resultsBox) {
  let timeout;

  searchInput.addEventListener("input", function () {
    clearTimeout(timeout);

    const query = this.value.trim();

    if (query.length < 2) {
      resultsBox.style.display = "none";
      resultsBox.innerHTML = "";
      return;
    }

    timeout = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then((res) => res.json())
        .then((data) => {
          resultsBox.innerHTML = "";

          if (data.length === 0) {
            resultsBox.innerHTML = `
              <div class="list-group-item text-muted">
                No products found
              </div>
            `;
          } else {
            data.forEach((item) => {
              const el = document.createElement("a");
              el.href = `/product/${item.slug}`;
              el.className =
                "list-group-item list-group-item-action d-flex align-items-center gap-2";

              el.innerHTML = `
                <img src="/static/uploads/${item.image}"
                     width="40" height="40"
                     style="object-fit:cover;border-radius:6px;">
                <div>
                  <div>${item.name}</div>
                  <small class="text-success"> £${item.price}</small>
                </div>
              `;

              resultsBox.appendChild(el);
            });
          }

          resultsBox.style.display = "block";
        });
    }, 300);
  });

  document.addEventListener("click", function (e) {
    if (
      !e.target.closest("#searchInput") &&
      !e.target.closest("#searchResults")
    ) {
      resultsBox.style.display = "none";
    }
  });
}
