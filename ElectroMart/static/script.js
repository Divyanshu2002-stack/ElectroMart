document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("searchInput");
    const categoryButtons = document.querySelectorAll(".category-btn");
    const productCards = document.querySelectorAll(".product-card");
    const noResults = document.getElementById("noResults");

    if (!searchInput || productCards.length === 0) {
        return;
    }

    let selectedCategory = "all";

    function filterProducts() {
        const searchText = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;

        productCards.forEach((card) => {
            const name = card.dataset.name || "";
            const category = card.dataset.category || "";

            const matchesSearch = name.includes(searchText);
            const matchesCategory =
                selectedCategory === "all" ||
                category === selectedCategory;

            const visible = matchesSearch && matchesCategory;

            card.hidden = !visible;

            if (visible) {
                visibleCount++;
            }
        });

        if (noResults) {
            noResults.hidden = visibleCount !== 0;
        }
    }

    searchInput.addEventListener("input", filterProducts);

    categoryButtons.forEach((button) => {
        button.addEventListener("click", () => {
            selectedCategory = button.dataset.category;

            categoryButtons.forEach((item) => {
                item.classList.toggle("active", item === button);
            });

            filterProducts();
        });
    });
});