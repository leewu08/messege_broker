document.addEventListener("DOMContentLoaded", () => {
  const username = window.username || `Anon-${Math.random().toString(36).slice(2, 6)}`;
  const socket = io(`/?user=${encodeURIComponent(username)}`);

  socket.on("user_list", (users) => {
    const userList = document.getElementById("user-list-ul");
    if (!userList) return;

    userList.innerHTML = ""; // 기존 목록 초기화

    // ✅ 중복 제거
    const uniqueUsers = [...new Set(users)];

    uniqueUsers.forEach((user) => {
      const li = document.createElement("li");

      if (user === username) {
        li.textContent = user; // 자기 자신은 클릭 불가
        userList.appendChild(li);
        return;
      }

      li.classList.add("user-dropdown");
      li.innerHTML = `
        <span>${user}</span>
        <div class="user-dropdown-content">
          <button onclick="alert('🔍 ${user} 상세정보 보기')">상세정보</button>
          <button onclick="alert('📝 ${user}의 작성글 보기')">작성글 보기</button>
          <button onclick="startDM('${user}')">1:1 대화하기</button>
        </div>
      `;

      li.querySelector("span").onclick = () => {
        const content = li.querySelector(".user-dropdown-content");
        const all = document.querySelectorAll(".user-dropdown-content");
        all.forEach(el => {
          if (el !== content) el.style.display = "none";
        });
        content.style.display = content.style.display === "block" ? "none" : "block";
      };

      userList.appendChild(li);
    });
  });

  document.addEventListener("click", (e) => {
    const all = document.querySelectorAll(".user-dropdown-content");
    all.forEach(menu => {
      if (!menu.parentElement.contains(e.target)) {
        menu.style.display = "none";
      }
    });
  });
});

function startDM(targetUser) {
  const room = generateDMRoom(window.username, targetUser);
  joinRoom(room); // 네가 이미 만든 함수일 거야
}

function generateDMRoom(userA, userB) {
  const [u1, u2] = [userA, userB].sort();
  return `dm_${u1}_${u2}`;
}