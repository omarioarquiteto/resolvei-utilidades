
(function () {
  "use strict";
  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const safeGet = (key, fallback) => {
    try { const value = localStorage.getItem(key); return value === null ? fallback : value; }
    catch (_) { return fallback; }
  };
  const safeSet = (key, value) => { try { localStorage.setItem(key, String(value)); } catch (_) {} };
  const shuffle = (items) => {
    const arr = items.slice();
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  };
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, ch => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  }[ch]));
  const gameCatalog = [
    {id:"chess", title:"Xadrez", icon:"♟️", category:"estrategia", label:"Estratégia", difficulty:"Intermediário", time:"5–20 min", desc:"Planeje jogadas, antecipe respostas e dispute uma partida no mesmo dispositivo.", color:"#e8e0ff", glow:"#d5c8ff"},
    {id:"sudoku", title:"Sudoku", icon:"🔢", category:"logica", label:"Lógica", difficulty:"Fácil a difícil", time:"5–15 min", desc:"Complete a grade sem repetir números nas linhas, colunas e blocos.", color:"#d9f7ee", glow:"#c4f1e3"},
    {id:"crossword", title:"Palavras cruzadas", icon:"🔤", category:"palavras", label:"Palavras", difficulty:"Fácil, médio e difícil", time:"Livre", desc:"Um livreto clássico, com dicas em quadrinhos e modo tela cheia para jogar no celular.", color:"#ffe1ef", glow:"#ffc9e1"},
    {id:"tetris", title:"Tetris", icon:"🧱", category:"agilidade", label:"Agilidade", difficulty:"Ritmo crescente", time:"Livre", desc:"Encaixe as peças, complete linhas e tente bater seu recorde.", color:"#ffe8c9", glow:"#ffddb1"},
    {id:"2048", title:"2048", icon:"🧩", category:"logica", label:"Lógica", difficulty:"Progressivo", time:"3–10 min", desc:"Junte blocos iguais, pense alguns movimentos à frente e alcance 2048.", color:"#e7e4ff", glow:"#d4ceff"},
    {id:"memory", title:"Jogo da memória", icon:"🧠", category:"memoria", label:"Memória", difficulty:"Iniciante", time:"2–5 min", desc:"Encontre os pares e tente completar o tabuleiro com menos tentativas.", color:"#fff0bd", glow:"#ffe69b"},
    {id:"simon", title:"Sequência luminosa", icon:"✨", category:"memoria", label:"Memória", difficulty:"Ritmo crescente", time:"1–5 min", desc:"Observe a sequência de cores e repita-a na ordem certa.", color:"#d7e9ff", glow:"#c4ddff"},
    {id:"wordsearch", title:"Caça-palavras", icon:"🔎", category:"palavras", label:"Palavras", difficulty:"Iniciante", time:"3–7 min", desc:"Localize palavras escondidas na horizontal, vertical ou diagonal.", color:"#dbf7dc", glow:"#c1efc5"},
    {id:"jungla-run", title:"Jungla Run", icon:"🌿", category:"plataforma", label:"Plataforma 2D", difficulty:"Exploração", time:"Livre", desc:"Uma aventura colorida com saltos duplos, cristais, criaturas, caminhos elevados e um portal guardado.", embedUrl:"/game-platformer.html", color:"#d9f6dc", glow:"#bfecc5"},
    {id:"stellar-defense", title:"Stellar Defense", icon:"🚀", category:"arcade", label:"Combate espacial", difficulty:"Ondas crescentes", time:"Livre", desc:"Pilote uma nave de combate, enfrente esquadrões de drones, colete módulos e derrote naves capitãs em uma batalha sci-fi com efeitos luminosos.", embedUrl:"/game-space-invaders.html", color:"#dceaff", glow:"#c4d8ff"},
    {id:"war-territorial", title:"Conquista Mundial", icon:"🌍", category:"estrategia", label:"Estratégia por turnos", difficulty:"Intermediário", time:"20–60 min", desc:"Conquiste territórios, distribua reforços, ataque regiões vizinhas, mova exércitos e enfrente até cinco adversários controlados pelo computador.", embedUrl:"/game-conquista-mundial.html", color:"#ffe2d5", glow:"#ffc8b4"},
    {id:"operacao-delta", title:"Operação Delta", icon:"🎖️", category:"acao", label:"Ação lateral", difficulty:"Ação crescente", time:"Livre", desc:"Atravesse uma base militar, enfrente patrulhas, destrua barris, recolha suprimentos e encare um blindado de comando.", embedUrl:"/game-operacao-delta.html", color:"#e6f4ca", glow:"#caeaa0"}
  ];
  const categoryNames = {logica:"Lógica", estrategia:"Estratégia", memoria:"Memória", palavras:"Palavras", agilidade:"Agilidade", plataforma:"Plataforma", arcade:"Arcade", acao:"Ação"};
  let activeFilter = "todos";
  let activeGame = "";
  let cleanupJobs = [];
  let currentKeyHandler = null;

  function renderCatalog() {
    const query = $("#gameSearch").value.trim().toLocaleLowerCase("pt-BR");
    const filtered = gameCatalog.filter(game => {
      const hasCategory = activeFilter === "todos" || game.category === activeFilter;
      const text = (game.title + " " + game.desc + " " + game.label).toLocaleLowerCase("pt-BR");
      return hasCategory && text.includes(query);
    });
    $("#visibleCount").textContent = filtered.length;
    $("#noGames").hidden = filtered.length > 0;
    $("#gamesGrid").innerHTML = filtered.map(game =>
      '<article class="game-card" style="--card-color:' + game.color + ';--card-glow:' + game.glow + '">' +
        '<div class="game-card-top"><div class="game-art-icon">' + game.icon + '</div><span class="game-badge">' + game.label + '</span></div>' +
        '<h3>' + game.title + '</h3><p>' + game.desc + '</p>' +
        '<div class="game-card-meta"><span>◷ ' + game.time + '</span><span>✦ ' + game.difficulty + '</span></div>' +
        '<button class="play-game" type="button" data-play="' + game.id + '">Jogar agora <span>↗</span></button>' +
      '</article>'
    ).join("");
    $$("#gamesGrid [data-play]").forEach(button => button.addEventListener("click", () => openGame(button.dataset.play)));
  }

  function updatePlayedCount() { $("#gamesPlayed").textContent = safeGet("resolveiGamesPlayed", "0"); }
  function cleanRuntime() {
    cleanupJobs.forEach(fn => { try { fn(); } catch (_) {} });
    cleanupJobs = [];
    if (currentKeyHandler) {
      document.removeEventListener("keydown", currentKeyHandler);
      currentKeyHandler = null;
    }
  }
  function addKeyHandler(handler) {
    currentKeyHandler = handler;
    document.addEventListener("keydown", handler);
    cleanupJobs.push(() => document.removeEventListener("keydown", handler));
  }
  function openGame(id) {
    const game = gameCatalog.find(item => item.id === id);
    if (!game) return;
    if (game.externalUrl) {
      const played = Number(safeGet("resolveiGamesPlayed", "0")) + 1;
      safeSet("resolveiGamesPlayed", played);
      updatePlayedCount();
      window.open(game.externalUrl, "_blank", "noopener,noreferrer");
      return;
    }
    cleanRuntime();
    activeGame = id;
    document.body.classList.toggle("crossword-active", id === "crossword");
    $("#heroSection").hidden = true;
    $("#catalogSection").hidden = true;
    $(".up-next-section").hidden = true;
    $(".games-footer").hidden = true;
    $("#gameStage").hidden = false;
    $("#stageTitle").textContent = game.title;
    $("#stageCategory").textContent = categoryNames[game.category] || game.label;
    $("#stageDescription").textContent = game.desc;
    $("#stageControls").innerHTML = "";
    $("#gameMount").innerHTML = "";
    const played = Number(safeGet("resolveiGamesPlayed", "0")) + 1;
    safeSet("resolveiGamesPlayed", played);
    updatePlayedCount();
    const mount = $("#gameMount");
    if (id === "sudoku") initSudoku(mount);
    if (id === "chess") initChess(mount);
    if (id === "crossword") initEmbeddedGame(mount, "/games/palavras-cruzadas/index.html", game.title);
    if (id === "tetris") initTetris(mount);
    if (id === "2048") init2048(mount);
    if (id === "memory") initMemory(mount);
    if (id === "simon") initSimon(mount);
    if (id === "wordsearch") initWordsearch(mount);
    if (game.embedUrl) initEmbeddedGame(mount, game.embedUrl, game.title);
    window.scrollTo({top:0, behavior:"smooth"});
  }

  function initEmbeddedGame(mount, src, title) {
    mount.innerHTML =
      '<div class="embedded-game-shell">' +
        '<div class="embedded-game-toolbar"><span>🎮 <strong>' + escapeHtml(title) + '</strong></span>' +
        '<a class="game-btn" href="' + src + '" target="_blank" rel="noopener noreferrer">Abrir em tela separada ↗</a></div>' +
        '<iframe class="embedded-game-frame" src="' + src + '" title="' + escapeHtml(title) + '" allow="fullscreen; autoplay" allowfullscreen></iframe>' +
      '</div>';
  }
  function closeGame() {
    cleanRuntime();
    activeGame = "";
    document.body.classList.remove("crossword-active");
    $("#gameStage").hidden = true;
    $("#heroSection").hidden = false;
    $("#catalogSection").hidden = false;
    $(".up-next-section").hidden = false;
    $(".games-footer").hidden = false;
    $("#gameMount").innerHTML = "";
    renderCatalog();
    window.scrollTo({top:0, behavior:"smooth"});
  }
  $("#stageBack").addEventListener("click", closeGame);
  $("#gameSearch").addEventListener("input", renderCatalog);
  $$("#gameFilters [data-filter]").forEach(button => button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    $$("#gameFilters [data-filter]").forEach(item => item.classList.toggle("active", item === button));
    renderCatalog();
  }));
  document.addEventListener("keydown", event => {
    if (event.key === "/" && !$("#gameStage").hidden && activeGame) return;
    if (event.key === "/" && $("#gameStage").hidden && !["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) {
      event.preventDefault(); $("#gameSearch").focus();
    }
    if (event.key === "Escape" && activeGame) closeGame();
  });
  updatePlayedCount();
  renderCatalog();

  function initSudoku(mount) {
    mount.innerHTML =
      '<div class="board-wrap"><div><div class="sudoku-grid" id="sudokuGrid" role="group" aria-label="Grade de Sudoku"></div>' +
      '<div class="number-pad" id="sudokuPad">' + [1,2,3,4,5,6,7,8,9].map(n => '<button type="button" data-number="' + n + '">' + n + '</button>').join("") +
      '<button type="button" data-number="0">⌫</button></div></div>' +
      '<aside class="board-side"><div class="game-stat-row"><div class="game-stat"><strong id="sudokuClock">00:00</strong><span>Tempo</span></div><div class="game-stat"><strong id="sudokuErrors">0</strong><span>Erros verificados</span></div></div>' +
      '<h3 class="board-title">Complete a grade</h3><p class="board-copy">Cada linha, coluna e bloco 3×3 deve conter os números de 1 a 9, sem repetição. Selecione uma célula e use o teclado ou os botões.</p>' +
      '<label for="sudokuDifficulty" class="sudoku-label">Dificuldade</label><select id="sudokuDifficulty" class="sudoku-select"><option value="easy">Fácil</option><option value="medium" selected>Médio</option><option value="hard">Difícil</option></select>' +
      '<div class="board-actions"><button class="game-btn primary" id="sudokuNew" type="button">Novo Sudoku</button><button class="game-btn" id="sudokuCheck" type="button">Conferir</button><button class="game-btn" id="sudokuHint" type="button">Dica</button></div>' +
      '<p class="inline-status" id="sudokuStatus" style="margin-top:13px">Escolha uma célula para começar.</p></aside></div>';
    const gridEl = $("#sudokuGrid", mount);
    const statusEl = $("#sudokuStatus", mount);
    let solution = [];
    let board = [];
    let selected = [0,0];
    let wrongCells = new Set();
    let errors = 0;
    let seconds = 0;
    let timerId = null;
    const shuffleRange = n => shuffle(Array.from({length:n}, (_,i)=>i));
    function makeSolution() {
      const bands = shuffleRange(3);
      const rows = bands.flatMap(b => shuffleRange(3).map(r => b*3+r));
      const stacks = shuffleRange(3);
      const cols = stacks.flatMap(s => shuffleRange(3).map(c => s*3+c));
      const digits = shuffle([1,2,3,4,5,6,7,8,9]);
      return rows.map(r => cols.map(c => digits[(r*3 + Math.floor(r/3) + c) % 9]));
    }
    function newPuzzle() {
      if (timerId) clearInterval(timerId);
      solution = makeSolution();
      board = solution.map(row => row.slice());
      const blankCount = {easy:34, medium:44, hard:53}[$("#sudokuDifficulty", mount).value] || 44;
      shuffle(Array.from({length:81}, (_,i)=>i)).slice(0, blankCount).forEach(index => board[Math.floor(index/9)][index%9] = 0);
      setPuzzleGiven();
      selected = [0,0]; wrongCells = new Set(); errors = 0; seconds = 0;
      $("#sudokuErrors", mount).textContent = "0";
      statusEl.textContent = "Novo desafio iniciado. Boa sorte!";
      statusEl.className = "inline-status";
      renderBoard();
      timerId = setInterval(() => {
        seconds++;
        $("#sudokuClock", mount).textContent = String(Math.floor(seconds/60)).padStart(2,"0") + ":" + String(seconds%60).padStart(2,"0");
      }, 1000);
    }
    function renderBoard() {
      const selectedValue = board[selected[0]][selected[1]];
      gridEl.innerHTML = board.map((row, r) => row.map((value,c) => {
        const given = solution[r][c] === value && value !== 0 && !isEditable(r,c);
        const isSelected = selected[0]===r && selected[1]===c;
        const related = selected[0]===r || selected[1]===c || (Math.floor(selected[0]/3)===Math.floor(r/3) && Math.floor(selected[1]/3)===Math.floor(c/3));
        const same = selectedValue !== 0 && value === selectedValue;
        const wrong = wrongCells.has(r + "," + c);
        const classes = ["sudoku-cell", given ? "given" : "", isSelected ? "selected" : "", !isSelected && related ? "related" : "", same ? "same-number" : "", wrong ? "wrong" : ""].filter(Boolean).join(" ");
        return '<button type="button" class="' + classes + '" data-r="' + r + '" data-c="' + c + '" aria-label="Linha ' + (r+1) + ', coluna ' + (c+1) + (value ? ', número ' + value : ', vazia') + '">' + (value || "") + '</button>';
      }).join("")).join("");
    }
    function isEditable(r,c) { return !puzzleGiven[r][c]; }
    let puzzleGiven = [];
    function setPuzzleGiven() { puzzleGiven = board.map(row => row.map(v => v !== 0)); }
    function enterNumber(number) {
      const r = selected[0], c = selected[1];
      if (puzzleGiven[r] && puzzleGiven[r][c]) return;
      board[r][c] = number;
      wrongCells.delete(r + "," + c);
      renderBoard();
      if (board.every((row,ri) => row.every((v,ci) => v === solution[ri][ci]))) {
        if (timerId) clearInterval(timerId);
        statusEl.textContent = "Perfeito! Sudoku concluído em " + $("#sudokuClock", mount).textContent + ".";
        statusEl.className = "inline-status success";
      }
    }
    gridEl.addEventListener("click", event => {
      const cell = event.target.closest("[data-r]");
      if (!cell) return;
      selected = [Number(cell.dataset.r), Number(cell.dataset.c)];
      renderBoard();
    });
    $("#sudokuPad", mount).addEventListener("click", event => {
      const button = event.target.closest("[data-number]");
      if (button) enterNumber(Number(button.dataset.number));
    });
    $("#sudokuNew", mount).addEventListener("click", newPuzzle);
    $("#sudokuCheck", mount).addEventListener("click", () => {
      wrongCells = new Set();
      for (let r=0;r<9;r++) for (let c=0;c<9;c++) if (board[r][c] && board[r][c] !== solution[r][c]) wrongCells.add(r + "," + c);
      errors += wrongCells.size ? 1 : 0;
      $("#sudokuErrors", mount).textContent = errors;
      renderBoard();
      if (wrongCells.size) {
        statusEl.textContent = wrongCells.size + " número(s) não correspondem à solução. Revise as células em rosa.";
        statusEl.className = "inline-status warning";
      } else if (board.every((row,ri) => row.every((v,ci) => v === solution[ri][ci]))) {
        if (timerId) clearInterval(timerId);
        statusEl.textContent = "Grade correta! Desafio concluído.";
        statusEl.className = "inline-status success";
      } else {
        statusEl.textContent = "Até aqui está correto. Ainda faltam " + board.flat().filter(v => !v).length + " células.";
        statusEl.className = "inline-status";
      }
    });
    $("#sudokuHint", mount).addEventListener("click", () => {
      for (let r=0;r<9;r++) for (let c=0;c<9;c++) if (!board[r][c]) {
        selected = [r,c]; board[r][c] = solution[r][c]; wrongCells.delete(r + "," + c); renderBoard();
        statusEl.textContent = "Dica aplicada. Continue resolvendo!";
        statusEl.className = "inline-status";
        return;
      }
      statusEl.textContent = "Não há células vazias.";
      statusEl.className = "inline-status success";
    });
    $("#sudokuDifficulty", mount).addEventListener("change", newPuzzle);
    const handler = event => {
      if (activeGame !== "sudoku" || ["INPUT","SELECT","TEXTAREA"].includes(document.activeElement.tagName)) return;
      if (/^[1-9]$/.test(event.key)) { event.preventDefault(); enterNumber(Number(event.key)); }
      if (event.key === "Backspace" || event.key === "Delete" || event.key === "0") { event.preventDefault(); enterNumber(0); }
      const [r,c] = selected;
      if (event.key === "ArrowUp") { event.preventDefault(); selected=[Math.max(0,r-1),c]; renderBoard(); }
      if (event.key === "ArrowDown") { event.preventDefault(); selected=[Math.min(8,r+1),c]; renderBoard(); }
      if (event.key === "ArrowLeft") { event.preventDefault(); selected=[r,Math.max(0,c-1)]; renderBoard(); }
      if (event.key === "ArrowRight") { event.preventDefault(); selected=[r,Math.min(8,c+1)]; renderBoard(); }
    };
    addKeyHandler(handler);
    cleanupJobs.push(() => { if (timerId) clearInterval(timerId); });
    newPuzzle();
    renderBoard();
  }

  function initChess(mount) {
    mount.innerHTML = '<div class="chess-layout"><div><div class="chess-board" id="chessBoard" aria-label="Tabuleiro de xadrez"></div><p class="game-instructions">Clique em uma peça e depois na casa de destino. Toque em uma peça novamente para cancelar a seleção.</p></div>' +
      '<aside class="chess-side"><div class="chess-turn" id="chessStatus">Carregando tabuleiro…</div><p class="board-copy">Partida local para duas pessoas, no mesmo dispositivo. As jogadas legais são verificadas automaticamente.</p>' +
      '<h3 class="board-title">Jogadas</h3><div class="move-list" id="chessMoves">A partida ainda não começou.</div><div class="board-actions"><button class="game-btn primary" id="chessNew" type="button">Nova partida</button><button class="game-btn" id="chessUndo" type="button">Desfazer jogada</button><button class="game-btn" id="chessFlip" type="button">Virar tabuleiro</button></div></aside></div>';
    const boardEl = $("#chessBoard", mount);
    const statusEl = $("#chessStatus", mount);
    const movesEl = $("#chessMoves", mount);
    if (typeof window.Chess !== "function") {
      boardEl.innerHTML = '<p style="padding:20px;color:white">Não foi possível carregar o motor de xadrez. Confira sua conexão com a internet e recarregue a página.</p>';
      statusEl.textContent = "Motor de xadrez indisponível";
      return;
    }
    let game = new window.Chess();
    let selected = null;
    let legal = [];
    let flipped = false;
    const symbols = {w:{k:"♔",q:"♕",r:"♖",b:"♗",n:"♘",p:"♙"}, b:{k:"♚",q:"♛",r:"♜",b:"♝",n:"♞",p:"♟"}};
    function squareName(row,col) { return String.fromCharCode(97+col) + (8-row); }
    function renderBoard() {
      const ranks = flipped ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
      const files = flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
      const validTargets = legal.map(move=>move.to);
      boardEl.innerHTML = ranks.flatMap(rank => files.map(file => {
        const row = 7-rank;
        const square = String.fromCharCode(97+file) + (rank+1);
        const piece = game.get(square);
        const light = (rank+file)%2===1;
        let classes = "chess-square " + (light ? "light" : "dark");
        if (selected === square) classes += " selected";
        if (validTargets.includes(square)) classes += piece ? " capture" : " legal";
        return '<button type="button" class="' + classes + '" data-square="' + square + '" aria-label="' + square + (piece ? " peça " + piece.type : "") + '">' + (piece ? '<span class="' + (piece.color==="w" ? "white-piece" : "black-piece") + '">' + symbols[piece.color][piece.type] + '</span>' : "") + '</button>';
      })).join("");
      if (game.game_over()) {
        if (game.in_checkmate()) statusEl.textContent = "Xeque-mate! Vitória das " + (game.turn()==="w" ? "pretas" : "brancas") + ".";
        else statusEl.textContent = "Partida encerrada em empate.";
      } else {
        statusEl.textContent = (game.turn()==="w" ? "Brancas" : "Pretas") + " jogam" + (game.in_check() ? " — xeque!" : ".");
      }
      const history = game.history();
      movesEl.innerHTML = history.length ? history.reduce((html, move, index) => {
        if (index%2===0) html += '<div><strong>' + (Math.floor(index/2)+1) + '.</strong> ';
        html += escapeHtml(move) + (index%2===1 ? '</div>' : ' ');
        return html;
      }, "") : "A partida ainda não começou.";
    }
    boardEl.addEventListener("click", event => {
      const button = event.target.closest("[data-square]");
      if (!button || game.game_over()) return;
      const square = button.dataset.square;
      if (selected && legal.some(move => move.to === square)) {
        const move = game.move({from:selected, to:square, promotion:"q"});
        if (move) { selected = null; legal = []; renderBoard(); return; }
      }
      const piece = game.get(square);
      if (piece && piece.color === game.turn()) {
        if (selected === square) { selected = null; legal = []; }
        else { selected = square; legal = game.moves({square:square, verbose:true}); }
      } else { selected = null; legal = []; }
      renderBoard();
    });
    $("#chessNew", mount).addEventListener("click", () => { game = new window.Chess(); selected=null; legal=[]; renderBoard(); });
    $("#chessUndo", mount).addEventListener("click", () => { game.undo(); selected=null; legal=[]; renderBoard(); });
    $("#chessFlip", mount).addEventListener("click", () => { flipped=!flipped; renderBoard(); });
    renderBoard();
  }

  function initTetris(mount) {
    mount.innerHTML = '<div class="tetris-layout"><div class="tetris-canvas-wrap"><canvas id="tetrisCanvas" class="tetris-canvas" width="300" height="600" aria-label="Tabuleiro de Tetris"></canvas></div>' +
      '<aside class="tetris-side"><div class="game-stat-row"><div class="game-stat"><strong id="tetrisScore">0</strong><span>Pontos</span></div><div class="game-stat"><strong id="tetrisLines">0</strong><span>Linhas</span></div><div class="game-stat"><strong id="tetrisLevel">1</strong><span>Nível</span></div></div>' +
      '<p class="board-copy">Setas movem as peças; ↑ gira; espaço derruba. No celular, use os controles abaixo.</p><p class="inline-status" id="tetrisStatus">Boa sorte!</p>' +
      '<div class="tetris-controls"><button type="button" data-tetris="left" aria-label="Mover para a esquerda">←</button><button type="button" data-tetris="rotate" aria-label="Girar">↻</button><button type="button" data-tetris="right" aria-label="Mover para a direita">→</button><button type="button" data-tetris="down" class="wide-control">↓ Descer</button><button type="button" data-tetris="drop" class="wide-control">⤓ Queda instantânea</button><button type="button" data-tetris="pause" class="wide-control">Pausar / continuar</button><button type="button" data-tetris="restart" class="wide-control">Reiniciar partida</button></div></aside></div>';
    const canvas = $("#tetrisCanvas", mount);
    const ctx = canvas.getContext("2d");
    const W = 10, H = 20, CELL = 30;
    const shapes = [
      {matrix:[[1,1,1,1]], color:"#5cd9d0"},
      {matrix:[[1,1],[1,1]], color:"#ffcf6b"},
      {matrix:[[0,1,0],[1,1,1]], color:"#a58bff"},
      {matrix:[[1,0,0],[1,1,1]], color:"#ff9b75"},
      {matrix:[[0,0,1],[1,1,1]], color:"#76a8ff"},
      {matrix:[[0,1,1],[1,1,0]], color:"#8de1a9"},
      {matrix:[[1,1,0],[0,1,1]], color:"#ff83b8"}
    ];
    let board, piece, score, lines, level, paused, over, intervalId, best = Number(safeGet("resolveiTetrisBest","0"));
    function emptyBoard() { return Array.from({length:H},()=>Array(W).fill(0)); }
    function newPiece() {
      const chosen = shapes[Math.floor(Math.random()*shapes.length)];
      return {matrix:chosen.matrix.map(row=>row.slice()), color:chosen.color, x:Math.floor((W-chosen.matrix[0].length)/2), y:0};
    }
    function collides(matrix,x,y) {
      for (let py=0;py<matrix.length;py++) for (let px=0;px<matrix[py].length;px++) if (matrix[py][px]) {
        const bx=x+px, by=y+py;
        if (bx<0 || bx>=W || by>=H || (by>=0 && board[by][bx])) return true;
      }
      return false;
    }
    function drawCell(x,y,color) {
      ctx.fillStyle = color; ctx.fillRect(x*CELL+1,y*CELL+1,CELL-2,CELL-2);
      ctx.fillStyle = "rgba(255,255,255,.22)"; ctx.fillRect(x*CELL+3,y*CELL+3,CELL-6,4);
    }
    function draw() {
      ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle="#17132d"; ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.strokeStyle="rgba(255,255,255,.055)"; ctx.lineWidth=1;
      for(let x=0;x<=W;x++){ctx.beginPath();ctx.moveTo(x*CELL,0);ctx.lineTo(x*CELL,canvas.height);ctx.stroke();}
      for(let y=0;y<=H;y++){ctx.beginPath();ctx.moveTo(0,y*CELL);ctx.lineTo(canvas.width,y*CELL);ctx.stroke();}
      board.forEach((row,y)=>row.forEach((cell,x)=>{if(cell)drawCell(x,y,cell);}));
      if(piece) piece.matrix.forEach((row,y)=>row.forEach((cell,x)=>{if(cell)drawCell(piece.x+x,piece.y+y,piece.color);}));
      if(paused || over) {
        ctx.fillStyle="rgba(27,20,57,.78)";ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.fillStyle="white";ctx.textAlign="center";ctx.font="bold 25px system-ui";
        ctx.fillText(over?"FIM DE JOGO":"PAUSADO",canvas.width/2,canvas.height/2);
        ctx.font="14px system-ui";ctx.fillText(over?"Reinicie para tentar de novo":"Toque em continuar",canvas.width/2,canvas.height/2+29);
      }
    }
    function updateStats() {
      $("#tetrisScore",mount).textContent=score;
      $("#tetrisLines",mount).textContent=lines;
      $("#tetrisLevel",mount).textContent=level;
    }
    function setStatus(text, kind) {
      const element=$("#tetrisStatus",mount);element.textContent=text;element.className="inline-status"+(kind?" "+kind:"");
    }
    function merge() {
      piece.matrix.forEach((row,y)=>row.forEach((cell,x)=>{if(cell && piece.y+y>=0)board[piece.y+y][piece.x+x]=piece.color;}));
    }
    function clearLines() {
      let count=0;
      for(let y=H-1;y>=0;y--) if(board[y].every(Boolean)){board.splice(y,1);board.unshift(Array(W).fill(0));count++;y++;}
      if(count){lines+=count;score += [0,100,300,500,800][count]||count*250;level=Math.floor(lines/10)+1;setStatus(count+" linha(s) eliminada(s)!","success");}
    }
    function drop() {
      if(paused||over)return;
      if(!collides(piece.matrix,piece.x,piece.y+1)){piece.y++;}
      else {
        merge();clearLines();piece=newPiece();
        if(collides(piece.matrix,piece.x,piece.y)){over=true;setStatus("Fim de jogo. Sua pontuação: "+score+".","warning");}
      }
      updateStats();draw();
      if(level!==lastLevel){lastLevel=level;setTimer();}
    }
    let lastLevel=1;
    function setTimer() {
      if(intervalId)clearInterval(intervalId);
      intervalId=setInterval(drop,Math.max(95,620-(level-1)*45));
    }
    function move(dx) { if(!paused&&!over&&!collides(piece.matrix,piece.x+dx,piece.y)){piece.x+=dx;draw();} }
    function rotate() {
      if(paused||over)return;
      const rotated=piece.matrix[0].map((_,i)=>piece.matrix.map(row=>row[i]).reverse());
      if(!collides(rotated,piece.x,piece.y)){piece.matrix=rotated;draw();}
    }
    function hardDrop() {
      if(paused||over)return;
      let distance=0;while(!collides(piece.matrix,piece.x,piece.y+1)){piece.y++;distance++;}
      score+=distance*2;drop();
    }
    function restart() {
      if(intervalId)clearInterval(intervalId);
      board=emptyBoard();piece=newPiece();score=0;lines=0;level=1;paused=false;over=false;lastLevel=1;
      updateStats();setStatus("Boa sorte!");setTimer();draw();
    }
    function act(action) {
      if(action==="left")move(-1);
      if(action==="right")move(1);
      if(action==="down")drop();
      if(action==="rotate")rotate();
      if(action==="drop")hardDrop();
      if(action==="pause"&&!over){paused=!paused;setStatus(paused?"Jogo pausado.":"Vamos continuar!");draw();}
      if(action==="restart")restart();
      if(score>best){best=score;safeSet("resolveiTetrisBest",best);}
    }
    $$(".tetris-controls [data-tetris]",mount).forEach(button=>button.addEventListener("click",()=>act(button.dataset.tetris)));
    const handler=event=>{
      if(activeGame!=="tetris"||["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName))return;
      const actions={ArrowLeft:"left",ArrowRight:"right",ArrowDown:"down",ArrowUp:"rotate"," ":"drop",p:"pause",P:"pause"};
      if(actions[event.key]){event.preventDefault();act(actions[event.key]);}
    };
    addKeyHandler(handler);
    cleanupJobs.push(()=>{if(intervalId)clearInterval(intervalId);});
    restart();
  }

  function init2048(mount) {
    mount.innerHTML = '<div class="game2048"><div class="game2048-header"><div><h3 class="board-title">Combine os números</h3><p class="board-copy">Use as setas para mover. Blocos iguais se juntam e viram um só.</p></div><div class="game2048-score">Pontos <strong id="score2048">0</strong></div></div>' +
      '<div id="board2048" class="game2048-board" role="group" aria-label="Tabuleiro 2048"></div><div class="game2048-controls"><button type="button" data-dir="up">↑</button><button type="button" data-dir="left">←</button><button type="button" data-dir="down">↓</button><button type="button" data-dir="right">→</button></div>' +
      '<div style="display:flex;justify-content:center;gap:8px;margin-top:14px"><button class="game-btn primary" id="restart2048" type="button">Novo jogo</button><span class="inline-status" id="status2048">Alcance 2048!</span></div></div>';
    const boardEl=$("#board2048",mount);let grid,score,over;
    function addTile() {
      const empty=[];for(let r=0;r<4;r++)for(let c=0;c<4;c++)if(!grid[r][c])empty.push([r,c]);
      if(empty.length){const cell=empty[Math.floor(Math.random()*empty.length)];grid[cell[0]][cell[1]]=Math.random()<.9?2:4;}
    }
    function render() {
      boardEl.innerHTML=grid.flat().map(value=>'<div class="tile2048 '+(value?"v"+value:"")+'">'+(value||"")+'</div>').join("");
      $("#score2048",mount).textContent=score;
    }
    function hasMoves() {
      for(let r=0;r<4;r++)for(let c=0;c<4;c++){
        if(!grid[r][c])return true;
        if(c<3&&grid[r][c]===grid[r][c+1])return true;
        if(r<3&&grid[r][c]===grid[r+1][c])return true;
      }return false;
    }
    function doMove(dir) {
      if(over)return;
      const before=JSON.stringify(grid);
      for(let i=0;i<4;i++){
        const coords=[];
        for(let k=0;k<4;k++){
          if(dir==="left")coords.push([i,k]);
          if(dir==="right")coords.push([i,3-k]);
          if(dir==="up")coords.push([k,i]);
          if(dir==="down")coords.push([3-k,i]);
        }
        const values=coords.map(pos=>grid[pos[0]][pos[1]]).filter(Boolean);
        const merged=[];
        for(let j=0;j<values.length;j++){
          if(values[j]===values[j+1]){const value=values[j]*2;merged.push(value);score+=value;j++;}
          else merged.push(values[j]);
        }
        while(merged.length<4)merged.push(0);
        coords.forEach((pos,k)=>grid[pos[0]][pos[1]]=merged[k]);
      }
      if(JSON.stringify(grid)===before)return;
      addTile();render();
      const status=$("#status2048",mount);
      if(grid.flat().includes(2048)){status.textContent="Você chegou a 2048!";status.className="inline-status success";}
      else if(!hasMoves()){over=true;status.textContent="Sem movimentos. Faça um novo jogo!";status.className="inline-status warning";}
      else {status.textContent="Continue combinando!";status.className="inline-status";}
    }
    function restart() {grid=Array.from({length:4},()=>Array(4).fill(0));score=0;over=false;addTile();addTile();render();$("#status2048",mount).textContent="Alcance 2048!";$("#status2048",mount).className="inline-status";}
    $$(".game2048-controls [data-dir]",mount).forEach(button=>button.addEventListener("click",()=>doMove(button.dataset.dir)));
    $("#restart2048",mount).addEventListener("click",restart);
    addKeyHandler(event=>{
      if(activeGame!=="2048"||["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName))return;
      const directions={ArrowLeft:"left",ArrowRight:"right",ArrowUp:"up",ArrowDown:"down"};
      if(directions[event.key]){event.preventDefault();doMove(directions[event.key]);}
    });
    restart();
  }

  function initMemory(mount) {
    mount.innerHTML = '<div style="max-width:500px;margin:auto;text-align:center"><div class="game-stat-row"><div class="game-stat"><strong id="memoryTurns">0</strong><span>Tentativas</span></div><div class="game-stat"><strong id="memoryPairs">0/8</strong><span>Pares</span></div></div><p class="board-copy">Vire duas cartas por vez para encontrar os pares. Tente terminar usando o menor número de tentativas.</p><div id="memoryBoard" class="memory-board"></div><p class="inline-status" id="memoryStatus" style="margin-top:15px">Encontre todos os pares!</p><button class="game-btn primary" id="memoryRestart" type="button" style="margin-top:10px">Embaralhar cartas</button></div>';
    const symbols=["🧠","🧩","♟️","🔢","🔍","🌀","🧮","💡"];
    const boardEl=$("#memoryBoard",mount);let cards=[],revealed=[],matched=new Set(),turns=0,locked=false,timeoutId=null;
    function render() {
      boardEl.innerHTML=cards.map((card,index)=>'<button type="button" class="memory-card '+(matched.has(index)?"matched":revealed.includes(index)?"revealed":"")+'" data-card="'+index+'" aria-label="'+(matched.has(index)||revealed.includes(index)?card:"Carta fechada")+'">'+(matched.has(index)||revealed.includes(index)?card:"?")+'</button>').join("");
      $("#memoryTurns",mount).textContent=turns;$("#memoryPairs",mount).textContent=matched.size/2+"/8";
    }
    function restart() {if(timeoutId)clearTimeout(timeoutId);cards=shuffle(symbols.concat(symbols));revealed=[];matched=new Set();turns=0;locked=false;render();$("#memoryStatus",mount).textContent="Encontre todos os pares!";$("#memoryStatus",mount).className="inline-status";}
    boardEl.addEventListener("click",event=>{
      const button=event.target.closest("[data-card]");if(!button||locked)return;
      const index=Number(button.dataset.card);
      if(matched.has(index)||revealed.includes(index))return;
      revealed.push(index);render();
      if(revealed.length===2){
        turns++;locked=true;
        if(cards[revealed[0]]===cards[revealed[1]]){
          revealed.forEach(i=>matched.add(i));revealed=[];locked=false;render();
          if(matched.size===cards.length){$("#memoryStatus",mount).textContent="Memória afiada! Você encontrou os 8 pares em "+turns+" tentativas.";$("#memoryStatus",mount).className="inline-status success";}
          else {$("#memoryStatus",mount).textContent="Par encontrado. Continue!";$("#memoryStatus",mount).className="inline-status";}
        }else{
          render();
          timeoutId=setTimeout(()=>{revealed=[];locked=false;render();},780);
        }
      }
    });
    $("#memoryRestart",mount).addEventListener("click",restart);
    cleanupJobs.push(()=>{if(timeoutId)clearTimeout(timeoutId);});
    restart();
  }

  function initSimon(mount) {
    mount.innerHTML = '<div class="simon-layout"><div class="game-stat-row" style="max-width:360px;margin:0 auto 14px"><div class="game-stat"><strong id="simonRound">0</strong><span>Sequência</span></div><div class="game-stat"><strong id="simonBest">0</strong><span>Recorde local</span></div></div><p class="board-copy">Observe as cores acenderem e repita a sequência na mesma ordem. A cada rodada, uma cor é adicionada.</p><div class="simon-board" id="simonBoard"><button class="simon-pad" data-pad="0" aria-label="Rosa"></button><button class="simon-pad" data-pad="1" aria-label="Verde"></button><button class="simon-pad" data-pad="2" aria-label="Roxo"></button><button class="simon-pad" data-pad="3" aria-label="Amarelo"></button></div><p class="inline-status" id="simonStatus">Pronto para começar?</p><button class="game-btn primary" id="simonStart" type="button" style="margin-top:12px">Começar sequência</button></div>';
    const boardEl=$("#simonBoard",mount);let sequence=[],inputIndex=0,playing=false,started=false,best=Number(safeGet("resolveiSimonBest","0")),timeouts=[];
    $("#simonBest",mount).textContent=best;
    function later(fn,ms){const id=setTimeout(fn,ms);timeouts.push(id);return id;}
    function flash(index,duration){
      const button=$('[data-pad="'+index+'"]',boardEl);if(button){button.classList.add("active");later(()=>button.classList.remove("active"),duration||270);}
    }
    function nextRound(){
      if(!started)return;
      sequence.push(Math.floor(Math.random()*4));inputIndex=0;playing=true;
      $("#simonRound",mount).textContent=sequence.length;
      $("#simonStatus",mount).textContent="Observe com atenção…";
      let i=0;
      const playNext=()=>{
        if(!playing||!started)return;
        if(i>=sequence.length){playing=false;$("#simonStatus",mount).textContent="Sua vez! Repita a sequência.";return;}
        flash(sequence[i++],350);later(playNext,650);
      };
      later(playNext,450);
    }
    function start(){timeouts.forEach(clearTimeout);timeouts=[];sequence=[];inputIndex=0;playing=false;started=true;$("#simonStart",mount).textContent="Recomeçar";$("#simonStatus",mount).textContent="Observe com atenção…";nextRound();}
    boardEl.addEventListener("click",event=>{
      const button=event.target.closest("[data-pad]");if(!button||playing||!started)return;
      const value=Number(button.dataset.pad);flash(value,180);
      if(value!==sequence[inputIndex]){
        playing=true;started=false;$("#simonStatus",mount).textContent="Quase! A sequência tinha "+sequence.length+" cores. Comece outra rodada.";
        $("#simonStatus",mount).className="inline-status warning";return;
      }
      inputIndex++;
      if(inputIndex===sequence.length){
        playing=true;
        if(sequence.length>best){best=sequence.length;safeSet("resolveiSimonBest",best);$("#simonBest",mount).textContent=best;}
        $("#simonStatus",mount).textContent="Muito bem! Preparando a próxima…";$("#simonStatus",mount).className="inline-status success";
        later(nextRound,850);
      }
    });
    $("#simonStart",mount).addEventListener("click",start);
    cleanupJobs.push(()=>{timeouts.forEach(clearTimeout);});
  }

  function initWordsearch(mount) {
    const words=["LOGICA","MEMORIA","XADREZ","SUDOKU","FOCO","IDEIA"];
    const size=9;let grid,placements,selected=null,found=[],foundCells=new Set();
    mount.innerHTML = '<div class="wordsearch-wrap"><div><div class="wordsearch-grid" id="wordsearchGrid" role="group" aria-label="Grade de caça-palavras"></div><p class="game-instructions">Selecione a primeira e a última letra de uma palavra em linha reta.</p></div><aside class="wordsearch-words"><h3>Encontre as palavras</h3><div class="word-pills" id="wordPills"></div><p class="board-copy" style="margin-top:14px">As palavras podem aparecer na horizontal, vertical ou diagonal, sempre em uma única direção.</p><p class="inline-status" id="wordsearchStatus">Boa busca!</p><button class="game-btn primary" id="wordsearchNew" type="button" style="margin-top:12px">Novo tabuleiro</button></aside></div>';
    const gridEl=$("#wordsearchGrid",mount);
    function makeBoard(){
      grid=Array.from({length:size},()=>Array(size).fill(""));
      placements=[];
      shuffle(words).forEach(word=>{
        let placed=false;
        for(let attempt=0;attempt<350&&!placed;attempt++){
          const dirs=shuffle([[0,1],[1,0],[1,1]]);
          const [dr,dc]=dirs[0];const r=Math.floor(Math.random()*size),c=Math.floor(Math.random()*size);
          const endR=r+dr*(word.length-1),endC=c+dc*(word.length-1);
          if(endR>=size||endC>=size)continue;
          let valid=true;
          for(let i=0;i<word.length;i++){const old=grid[r+dr*i][c+dc*i];if(old&&old!==word[i])valid=false;}
          if(!valid)continue;
          const cells=[];
          for(let i=0;i<word.length;i++){grid[r+dr*i][c+dc*i]=word[i];cells.push((r+dr*i)+","+(c+dc*i));}
          placements.push({word,cells});placed=true;
        }
      });
      const letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ";
      for(let r=0;r<size;r++)for(let c=0;c<size;c++)if(!grid[r][c])grid[r][c]=letters[Math.floor(Math.random()*letters.length)];
      selected=null;found=[];foundCells=new Set();render();
    }
    function render(){
      gridEl.innerHTML=grid.map((row,r)=>row.map((letter,c)=>{
        const key=r+","+c;return '<button type="button" class="wordsearch-cell '+(selected===key?"endpoint ":"")+(foundCells.has(key)?"found":"")+'" data-r="'+r+'" data-c="'+c+'" aria-label="Linha '+(r+1)+', coluna '+(c+1)+', '+letter+'">'+letter+'</button>';
      }).join("")).join("");
      $("#wordPills",mount).innerHTML=words.map(word=>'<span class="word-pill '+(found.includes(word)?"found":"")+'">'+word+'</span>').join("");
    }
    gridEl.addEventListener("click",event=>{
      const cell=event.target.closest("[data-r]");if(!cell)return;
      const key=cell.dataset.r+","+cell.dataset.c;
      if(!selected){selected=key;render();return;}
      if(selected===key){selected=null;render();return;}
      const [r1,c1]=selected.split(",").map(Number),r2=Number(cell.dataset.r),c2=Number(cell.dataset.c);
      const dr=Math.sign(r2-r1),dc=Math.sign(c2-c1);
      const length=Math.max(Math.abs(r2-r1),Math.abs(c2-c1))+1;
      if(r1!==r2&&c1!==c2&&Math.abs(r2-r1)!==Math.abs(c2-c1)){selected=key;render();$("#wordsearchStatus",mount).textContent="Escolha uma linha reta.";return;}
      let sequence="",cells=[];
      for(let i=0;i<length;i++){sequence+=grid[r1+dr*i][c1+dc*i];cells.push((r1+dr*i)+","+(c1+dc*i));}
      const word=words.find(item=>item===sequence||item===sequence.split("").reverse().join(""));
      if(word&&!found.includes(word)){
        found.push(word);cells.forEach(cellKey=>foundCells.add(cellKey));
        $("#wordsearchStatus",mount).textContent=found.length===words.length?"Encontrou todas! Excelente observação.":"Boa! "+word+" encontrada.";
        $("#wordsearchStatus",mount).className="inline-status success";
      }else{
        $("#wordsearchStatus",mount).textContent=word&&found.includes(word)?"Essa palavra já foi encontrada.":"Nenhuma palavra encontrada nesse trecho. Tente outra direção.";
        $("#wordsearchStatus",mount).className="inline-status";
      }
      selected=null;render();
    });
    $("#wordsearchNew",mount).addEventListener("click",makeBoard);
    makeBoard();
  }
})();
