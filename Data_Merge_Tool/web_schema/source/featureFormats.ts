// Data_Merge_Tool 使用的本地 featureFormats.ts 镜像占位文件。
// 作用：用于给 Tool 提供同步与解析入口。
// 正常流程：把 Web 仓库中的最新 featureFormats.ts 覆盖到这里，
// 然后在 Tool 中执行 sync-web-schema，生成 cache 下的解析结果。

export const worldIdToCodeMap = {
  zth: 0,
  naraku: 1,
  houtu: 2,
  eden: 3,
  laputa: 4,
  yunduan: 5,
};

export const specialClassList = ["ISG", "ISL", "ISP"];
