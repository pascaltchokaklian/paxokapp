var region_name_list = [],
    region_code_list = [],
    region_country_list = []
    region_id_list = [],
    year_displayed = '2023'
    
function country(value) {              

    const CombolisteRegion = document.getElementById("region");                
    CombolisteRegion.options.length = 0;
    choose_dept = new Option( "--- Département ---","");   
    CombolisteRegion.add(choose_dept); 
      for (i = 0; i < region_name_list.length; i += 1) {
        if (region_country_list[i] == value) {
        // création option                   
        one_dept = new Option( region_name_list[i],region_code_list[i]);        
        // ajout de l'option en fin
        CombolisteRegion.add(one_dept);        
        }
      }  
            
}

function region(value) {    
  const CombolisteRegion = document.getElementById("country");    
  var valeurselectionnee = CombolisteRegion.options[CombolisteRegion.selectedIndex].value;
  var codePays = valeurselectionnee.substring(0,2);  
  codePays = codePays + "-" + value  
  window.location.href="/cols_list/"+codePays+"/";
}

