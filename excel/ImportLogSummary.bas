Attribute VB_Name = "ImportLogSummary"
Option Explicit

' Imports tools/analyze_logs.py output and creates an operational QA pivot.
Public Sub ImportMQLogSummary()
    Dim csvPath As Variant, wb As Workbook, wsData As Worksheet, wsPivot As Worksheet
    Dim cache As PivotCache, table As PivotTable, sourceRange As Range

    csvPath = Application.GetOpenFilename("CSV Files (*.csv),*.csv", , "Select MQ log summary")
    If csvPath = False Then Exit Sub

    Application.ScreenUpdating = False
    Set wb = ThisWorkbook
    Set wsData = GetOrCreateSheet(wb, "LogData")
    wsData.Cells.Clear

    With wsData.QueryTables.Add(Connection:="TEXT;" & CStr(csvPath), Destination:=wsData.Range("A1"))
        .TextFileParseType = xlDelimited
        .TextFileCommaDelimiter = True
        .TextFilePlatform = 65001
        .Refresh BackgroundQuery:=False
        .Delete
    End With
    Set sourceRange = wsData.Range("A1").CurrentRegion
    If sourceRange.Rows.Count < 2 Then
        MsgBox "The selected report has no data rows.", vbExclamation
        GoTo CleanUp
    End If

    Application.DisplayAlerts = False
    On Error Resume Next
    wb.Worksheets("QA Pivot").Delete
    On Error GoTo 0
    Application.DisplayAlerts = True
    Set wsPivot = wb.Worksheets.Add(After:=wsData)
    wsPivot.Name = "QA Pivot"

    Set cache = wb.PivotCaches.Create(SourceType:=xlDatabase, SourceData:=sourceRange)
    Set table = cache.CreatePivotTable(TableDestination:=wsPivot.Range("A3"), TableName:="MQQualitySummary")
    With table
        .PivotFields("report_type").Orientation = xlPageField
        .PivotFields("stage").Orientation = xlRowField
        .PivotFields("error_type").Orientation = xlRowField
        .PivotFields("status").Orientation = xlColumnField
        .AddDataField .PivotFields("value"), "Count / Value", xlSum
    End With
    wsPivot.Range("A1").Value = "MQ File Processing QA Summary"
    wsPivot.Range("A1").Font.Bold = True
    wsPivot.Columns.AutoFit
    MsgBox "Import complete. Filter report_type to COUNT, FAILURE, or PERCENTILE.", vbInformation
CleanUp:
    Application.ScreenUpdating = True
End Sub

Private Function GetOrCreateSheet(ByVal wb As Workbook, ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set GetOrCreateSheet = wb.Worksheets(sheetName)
    On Error GoTo 0
    If GetOrCreateSheet Is Nothing Then
        Set GetOrCreateSheet = wb.Worksheets.Add
        GetOrCreateSheet.Name = sheetName
    End If
End Function
