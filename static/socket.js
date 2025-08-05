document.addEventListener("DOMContentLoaded", () => {
  const username = window.username || `Anon-${Math.random().toString(36).slice(2, 6)}`;
  const socket = io(`/?user=${encodeURIComponent(username)}`);

  socket.on("user_list", (users) => {
    const userList = document.getElementById("user-list-ul");
    if (!userList) return;

    userList.innerHTML = ""; // 기존 목록 초기화
    const uniqueUsers = [...new Set(users)];

    uniqueUsers.forEach((user) => {
      const li = document.createElement("li");
      li.classList.add("user-dropdown");

      const span = document.createElement("span");
      span.textContent = user;
      span.style.cursor = "pointer";
      span.style.fontWeight = "bold";

      li.appendChild(span);

      if (user !== username) {
        const menu = document.createElement("div");
        menu.classList.add("user-dropdown-content");
        menu.style.display = "none";

        const btnDetail = document.createElement("button");
        btnDetail.textContent = "상세정보";
        btnDetail.onclick = () => alert(`🔍 ${user} 상세정보 보기`);

        const btnPosts = document.createElement("button");
        btnPosts.textContent = "작성글 보기";
        btnPosts.onclick = () => alert(`📝 ${user}의 작성글 보기`);

        const btnDM = document.createElement("button");
        btnDM.textContent = "1:1 대화하기";
        btnDM.onclick = () => {
          const dmRoom = generateDMRoom(username, user);
          joinRoom(dmRoom);
        };

        menu.append(btnDetail, btnPosts, btnDM);
        li.appendChild(menu);

        span.addEventListener("click", (e) => {
          const all = document.querySelectorAll(".user-dropdown-content");
          all.forEach(m => { if (m !== menu) m.style.display = "none"; });
          menu.style.display = menu.style.display === "block" ? "none" : "block";
          e.stopPropagation(); // 문서 클릭 전파 방지
        });
      }

      userList.appendChild(li);
    });
  });

  // 바깥 클릭 시 모든 드롭다운 닫기
  document.addEventListener("click", () => {
    const all = document.querySelectorAll(".user-dropdown-content");
    all.forEach(menu => {
      menu.style.display = "none";
    });
  });
});

function generateDMRoom(userA, userB) {
  const [u1, u2] = [userA, userB].sort();
  return `dm_${u1}_${u2}`;
}

function joinRoom(roomName) {
  // 이건 너가 정의한 로직에 따라 연결
  window.location.href = `/chat?room=${roomName}`;