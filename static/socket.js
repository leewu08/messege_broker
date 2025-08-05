document.addEventListener("DOMContentLoaded", () => {
  const username = window.username || `Anon-${Math.random().toString(36).slice(2, 6)}`;
  const socket = io(`/?user=${encodeURIComponent(username)}`);

  socket.on("user_list", (users) => {
    const userList = document.getElementById("user-list-ul");
    if (!userList) return;

    userList.innerHTML = ""; // 기존 항목 제거

    users.forEach((user) => {
      const li = document.createElement("li");
      li.textContent = user;
      userList.appendChild(li);
    });
  });
});