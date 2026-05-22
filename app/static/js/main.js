// =========================
// REMOVE OLD HANDLER
// =========================
document.removeEventListener("click", window.__cartHandler);

// =========================
// MAIN EVENT DELEGATION
// =========================
window.__cartHandler = function (e) {
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
      .then(async (res) => {
        const text = await res.text();
        try {
          return JSON.parse(text);
        } catch (err) {
          console.error("Non-JSON response:", text);
          return null;
        }
      })
      .then((data) => {
        if (!data || !data.success) return;

        const row = removeBtn.closest("tr");
        if (row) row.remove();

        updateCartCount(data.cart_count);

        const totalEl = document.getElementById("cart-total");
        if (totalEl) totalEl.innerText = parseFloat(data.cart_total).toFixed(2);

        const drawer = document.getElementById("cartDrawer");
        if (drawer && drawer.classList.contains("active")) loadCartItems();

        checkCartEmpty();

        // ✅ Reset the add-to-cart button using slug from backend response
        const pageCartBtn = document.querySelector(
          `.add-to-cart-btn[data-slug="${data.slug}"]`,
        );
        if (pageCartBtn) {
          pageCartBtn.innerText = "Add to Cart";
          pageCartBtn.disabled = false;
          pageCartBtn.classList.add("btn-success");
          pageCartBtn.onclick = null;
        }
      });

    return;
  }

  // =========================
  // ADD TO CART
  // =========================
  const cartBtn = e.target.closest(".add-to-cart-btn");
  if (cartBtn) {
    e.preventDefault();

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

        updateCartCount(data.cart_count);

        cartBtn.innerText = "Added ✓";
        cartBtn.disabled = true;
        cartBtn.classList.add("btn-success");

        setTimeout(() => {
          cartBtn.innerText = "View Cart";
          cartBtn.disabled = false;
          cartBtn.classList.add("btn-success");
          cartBtn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (window.innerWidth < 768) {
              openCart(); // mobile: open drawer
            } else {
              window.location.href = "/cart"; // desktop: navigate to cart page
            }
          };
        }, 600);
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

        const qtyEl = document.getElementById(`qty-${itemId}`);
        const subEl = document.getElementById(`subtotal-${itemId}`);

        if (qtyEl) qtyEl.innerText = data.quantity;
        if (subEl) subEl.innerText = parseFloat(data.subtotal).toFixed(2);

        const totalEl = document.getElementById("cart-total");
        if (totalEl) totalEl.innerText = parseFloat(data.cart_total).toFixed(2);

        if (data.cart_count !== undefined) updateCartCount(data.cart_count);

        const drawer = document.getElementById("cartDrawer");
        if (drawer && drawer.classList.contains("active")) loadCartItems();
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

          // ✅ Reset the add-to-cart button when item is fully removed via decrease
          if (data.slug) {
            const pageCartBtn = document.querySelector(
              `.add-to-cart-btn[data-slug="${data.slug}"]`,
            );
            if (pageCartBtn) {
              pageCartBtn.innerText = "Add to Cart";
              pageCartBtn.disabled = false;
              pageCartBtn.classList.remove("btn-success");
              pageCartBtn.onclick = null;
            }
          }
        } else {
          const qtyEl = document.getElementById(`qty-${itemId}`);
          const subEl = document.getElementById(`subtotal-${itemId}`);

          if (qtyEl) qtyEl.innerText = data.quantity;
          if (subEl) subEl.innerText = parseFloat(data.subtotal).toFixed(2);
        }

        const totalEl = document.getElementById("cart-total");
        if (totalEl) totalEl.innerText = parseFloat(data.cart_total).toFixed(2);

        if (data.cart_count !== undefined) updateCartCount(data.cart_count);

        const drawer = document.getElementById("cartDrawer");
        if (drawer && drawer.classList.contains("active")) loadCartItems();

        checkCartEmpty();
      });

    return;
  }

  // =========================
  // WISHLIST ADD
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
        if (wishCountEl) wishCountEl.innerText = data.wishlist_count;

        wishlistBtn.classList.toggle("btn-danger");
        wishlistBtn.classList.toggle("btn-outline-danger");
      });

    return;
  }

  // =========================
  // WISHLIST REMOVE
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

        const wishCountEl = document.getElementById("wishlist-count");
        if (wishCountEl) wishCountEl.innerText = data.wishlist_count;

        const card = removeWishBtn.closest(".wishlist-card, .card, tr");
        if (card) card.remove();
      });

    return;
  }
};

// =========================
// ATTACH HANDLER
// =========================
document.addEventListener("click", window.__cartHandler);

// =========================
// EMPTY CART CHECK
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
// OPEN CART
// =========================
function openCart() {
  document.getElementById("cartDrawer").classList.add("active");
  loadCartItems();
}

// =========================
// LOAD MOBILE CART
// =========================
function loadCartItems() {
  fetch("/cart/data")
    .then((res) => res.json())
    .then((data) => {
      const container = document.getElementById("mobile-cart-items");
      const totalEl = document.getElementById("mobile-cart-total");

      if (!container) return;

      container.innerHTML = "";

      if (!data.items.length) {
        container.innerHTML = `
          <p class="text-center text-muted mt-3">
            Your cart is empty
          </p>
        `;
        if (totalEl) totalEl.innerText = "0";
        return;
      }

      let total = 0;

      data.items.forEach((item) => {
        total += Number(item.subtotal);

        container.innerHTML += `
          <div class="mobile-cart-card" data-slug="${item.slug}">
            <div class="d-flex gap-2 align-items-center">
              <img src="/static/uploads/${item.image}" width="60" class="rounded">
              <div>
                <strong>${item.name}</strong>
                <div>£${item.price}</div>
              </div>
            </div>

            <div class="d-flex justify-content-center gap-2 mt-2">
              <button class="btn btn-sm btn-outline-dark decrease-btn"
                data-id="${item.id}" data-csrf="${item.csrf}">-</button>

              <span id="qty-${item.id}">${item.quantity}</span>

              <button class="btn btn-sm btn-outline-dark increase-btn"
                data-id="${item.id}" data-csrf="${item.csrf}">+</button>
            </div>

            <div class="d-flex justify-content-between mx-3 mt-2">
              <small>Subtotal</small>
              <strong>£${parseFloat(item.subtotal).toFixed(2)}</strong>
            </div>

            <button class="btn btn-danger btn-sm w-100 mt-2 remove-item-btn"
              data-id="${item.id}" data-csrf="${item.csrf}" data-slug="${item.slug}">
              Remove
            </button>
          </div>
        `;
      });

      if (totalEl) totalEl.innerText = parseFloat(total).toFixed(2);
    });
}

// =========================
// CART COUNT SYNC
// =========================
function updateCartCount(count) {
  document.querySelectorAll(".cart-count").forEach((el) => {
    el.innerText = count;
  });
}

// =========================
// INITIAL SYNC
// =========================
document.addEventListener("DOMContentLoaded", function () {
  fetch("/cart/data-count")
    .then((res) => res.json())
    .then((data) => updateCartCount(data.cart_count))
    .catch(() => {});
});

function toggleCart() {
  const drawer = document.getElementById("cartDrawer");
  if (!drawer) return;

  drawer.classList.toggle("active");

  if (drawer.classList.contains("active")) {
    loadCartItems();
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
                  <small class="text-success">£${item.price}</small>
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
