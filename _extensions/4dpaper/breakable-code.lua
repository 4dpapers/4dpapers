local function escape_latex_char(ch)
  local escaped = {
    ["\\"] = "\\textbackslash{}",
    ["{"] = "\\{",
    ["}"] = "\\}",
    ["$"] = "\\$",
    ["&"] = "\\&",
    ["#"] = "\\#",
    ["%"] = "\\%",
    ["_"] = "\\_",
    ["^"] = "\\textasciicircum{}",
    ["~"] = "\\textasciitilde{}",
  }
  return escaped[ch] or ch
end

local function breakable_texttt(text)
  local parts = {}

  for i = 1, #text do
    local ch = text:sub(i, i)
    local prev = i > 1 and text:sub(i - 1, i - 1) or ""

    if i > 1 and ch:match("%u") and prev:match("%l") then
      table.insert(parts, "\\allowbreak{}")
    end

    table.insert(parts, escape_latex_char(ch))

    if ch == "/" or ch == "." or ch == "-" or ch == "_" then
      table.insert(parts, "\\allowbreak{}")
    end
  end

  return "\\texttt{" .. table.concat(parts) .. "}"
end

function Code(el)
  if FORMAT:match("latex") then
    return pandoc.RawInline("latex", breakable_texttt(el.text))
  end
end
